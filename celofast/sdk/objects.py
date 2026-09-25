"""Loaded business objects, typed collections, and relationships.

Instances are immutable snapshots: reading ``plant.country`` never performs a
request. Only collection and relationship fetches contact Celonis, through the
client that loaded the instance.

Each relationship is declared once, on a generated ``Links`` class::

    class PlantLinks(Links, source=Plant):
        materials = ToManyRelation(Material, on=(("id", "plant_id"),))

Read from the class (``Plant.relations.materials``) it builds predicates and
aggregates; read from an instance (``plant.links.materials``) it fetches the
related objects of that one object.

An event log is the history of its lead object: ``Event`` rows, reached
through an ``EventLogRelation`` that also filters lead objects by their
activities (``Line.relations.activities.contains("PostGoodsIssue")``).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, TypeVar, overload

from celofast.exceptions import (
    ObjectIdentityError,
    ObjectNotFoundError,
    ObjectValueError,
    QueryValidationError,
)
from celofast.sdk.capture import Source
from celofast.sdk.definitions import (
    Aggregate,
    AggregateFunction,
    EventDefinition,
    Field,
    ObjectDefinition,
    Operand,
    Predicate,
    Process,
    ProcessMode,
    Related,
    Sort,
)

if TYPE_CHECKING:
    from typing_extensions import Self

    from celofast.resources.knowledge_model import KnowledgeModelClient

O = TypeVar("O", bound="Object")
E = TypeVar("E", bound="Event")
T = TypeVar("T")
MAX_PAGE_SIZE = 10_000


@dataclass(frozen=True, kw_only=True)
class Object:
    """Base for generated value classes; each instance is one loaded object."""

    fields: ClassVar[ObjectDefinition]
    relations: ClassVar[type[Links]]
    """Relationship predicates of this type; see ``Links``."""
    # The loading client is attached per instance but is not a dataclass
    # field, so equality, repr, and dataclasses.asdict() see only values.
    _context: ClassVar[KnowledgeModelClient | None] = None

    def _attach(self: O, context: KnowledgeModelClient) -> O:
        object.__setattr__(self, "_context", context)
        return self

    @property
    def links(self) -> Links:
        """Relationships of this object; generated classes narrow this type."""
        return type(self).relations(self)


@dataclass(frozen=True, kw_only=True)
class Event(Object):
    """Base for generated event log rows: one event of one lead object.

    ``case`` is the lead object's key, ``activity`` the event type, and
    ``timestamp`` when it happened; ``links.case`` fetches the lead object.
    """

    fields: ClassVar[EventDefinition]


class Links:
    """Declares the relationships of one object type; bound to an object for traversal."""

    _source: ClassVar[type[Object]]

    def __init__(self, owner: Object) -> None:
        self._owner = owner

    def __init_subclass__(cls, *, source: type[Object], **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._source = source
        source.relations = cls
        for value in vars(cls).values():
            if isinstance(value, Relation):
                value.source = source


Object.relations = Links


class Relation(Generic[O]):
    """A relationship from ``source`` objects to ``target`` objects along a
    Data Model foreign key (or an event log's join to its lead object).

    ``on`` pairs (source field name, target field name).
    """

    cardinality: ClassVar[Literal["one", "many"]]
    name: str
    source: type[Object]

    def __init__(self, target: type[O], *, on: tuple[tuple[str, str], ...]) -> None:
        self.target, self.on = target, on

    def __set_name__(self, owner: type[Links], name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name!r} -> {self.target.fields.object_type})"

    def _related(self, predicate: Predicate | None) -> Predicate:
        self._check_target(predicate)
        return Related(self, predicate)

    def _check_target(self, predicate: Predicate | None) -> None:
        target = self.target.fields
        if predicate is not None and predicate.owner is not type(target):
            raise QueryValidationError(
                f"{self.name} relates to {target.object_type}; the predicate describes "
                f"{predicate.owner._object_type}."
            )

    def _collection(self, links: Links) -> ObjectCollection[O]:
        """The related objects of one loaded object."""
        session = links._owner._context
        if session is None:
            raise QueryValidationError(
                "This object was not loaded by a client; relationships cannot be fetched."
            )
        collection = session.objects(self.target)
        values = [(getattr(self.target.fields, right), getattr(links._owner, left)) for left, right in self.on]
        if any(value is None for _, value in values):
            # A null reference identifies no related objects; skip the request.
            return replace(collection, _empty=True)
        return collection.where(*(target_field.eq(value) for target_field, value in values))


class ToOneRelation(Relation[O]):
    """A to-one relationship."""

    cardinality = "one"

    @overload
    def __get__(self, links: None, owner: Any) -> Self: ...
    @overload
    def __get__(self, links: Links, owner: Any) -> ToOne[O]: ...
    def __get__(self, links: Links | None, owner: Any) -> Self | ToOne[O]:
        return self if links is None else ToOne(self._collection(links))

    def has(self, predicate: Predicate | None = None) -> Predicate:
        """The related object exists and, if given, matches ``predicate``."""
        return self._related(predicate)


class ToManyRelation(Relation[O]):
    """A to-many relationship.

    Aggregates compile to Pull-Up functions (PU_COUNT, PU_SUM, ...) on the
    source table; ``predicate`` limits which related objects count. Results
    are NULL when no related value exists, except the two counts (0).
    """

    cardinality = "many"

    @overload
    def __get__(self, links: None, owner: Any) -> Self: ...
    @overload
    def __get__(self, links: Links, owner: Any) -> ObjectCollection[O]: ...
    def __get__(self, links: Links | None, owner: Any) -> Self | ObjectCollection[O]:
        return self if links is None else self._collection(links)

    def any(self, predicate: Predicate | None = None) -> Predicate:
        """At least one related object exists and, if given, matches ``predicate``."""
        return self._related(predicate)

    def count(self, predicate: Predicate | None = None) -> Aggregate[int]:
        """Number of related objects (PU_COUNT)."""
        return self._aggregate("count", None, predicate)

    def count_distinct(self, field: Field[Any], predicate: Predicate | None = None) -> Aggregate[int]:
        """Number of distinct non-null values of a related field (PU_COUNT_DISTINCT)."""
        return self._aggregate("count_distinct", field, predicate)

    def sum(self, field: Field[T], predicate: Predicate | None = None) -> Aggregate[T]:
        """Sum of a numeric related field (PU_SUM)."""
        return self._aggregate("sum", field, predicate)

    def avg(self, field: Field[Any], predicate: Predicate | None = None) -> Aggregate[float | None]:
        """Average of a numeric related field, as a float (PU_AVG)."""
        return self._aggregate("avg", field, predicate)

    def min(self, field: Field[T], predicate: Predicate | None = None) -> Aggregate[T]:
        """Smallest related value (PU_MIN)."""
        return self._aggregate("min", field, predicate)

    def max(self, field: Field[T], predicate: Predicate | None = None) -> Aggregate[T]:
        """Largest related value (PU_MAX)."""
        return self._aggregate("max", field, predicate)

    def median(self, field: Field[T], predicate: Predicate | None = None) -> Aggregate[T]:
        """Median related value (PU_MEDIAN); for an even count, the upper middle value."""
        return self._aggregate("median", field, predicate)

    def _aggregate(
        self, function: AggregateFunction, field: Field[Any] | None, predicate: Predicate | None
    ) -> Aggregate[Any]:
        self._check_target(predicate)
        target = self.target.fields
        if field is None:
            field = target.key_fields[0]
        elif field.owner is not type(target):
            raise QueryValidationError(
                f"{function}() aggregates fields of {target.object_type}, not {field.owner._object_type}."
            )
        if function in ("sum", "avg", "median") and field.value_type not in ("int", "float"):
            raise ObjectValueError(f"{function}() needs a numeric field; {field.name} is {field.value_type}.")
        if function in ("min", "max") and field.value_type == "bool":
            raise ObjectValueError(f"{function}() needs an ordered field; {field.name} is boolean.")
        return Aggregate(self, function, field, predicate)


class EventLogRelation(ToManyRelation[E]):
    """The event log of a lead object: its events, in time order.

    Besides the to-many predicates and aggregates, it filters lead objects by
    the activities in their history, with ``MATCH_ACTIVITIES``. Activities are
    event types, named by table (``e_celonis_PostGoodsIssue``) or by type
    (``PostGoodsIssue``).
    """

    def contains(self, *activities: str) -> Predicate:
        """The history has every one of ``activities``, in any order."""
        return self._process("contains", activities)

    def excludes(self, *activities: str) -> Predicate:
        """The history has none of ``activities``; also true for an empty history."""
        return self._process("excludes", activities)

    def starts_with(self, *activities: str) -> Predicate:
        """The first activity is one of ``activities``."""
        return self._process("starts_with", activities)

    def ends_with(self, *activities: str) -> Predicate:
        """The last activity is one of ``activities``."""
        return self._process("ends_with", activities)

    def _process(self, mode: ProcessMode, activities: tuple[str, ...]) -> Predicate:
        if not activities:
            raise QueryValidationError(f"{mode}() needs at least one activity.")
        if not all(isinstance(activity, str) and activity for activity in activities):
            raise ObjectValueError(f"{mode}() activities are event type names.")
        known = self.target.fields._event_types
        return Process(self, mode, tuple(_event_type(activity, known) for activity in activities))


def _event_type(activity: str, known: tuple[str, ...]) -> str:
    """The event type table an activity names; unchecked when none are known."""
    if not known or activity in known:
        return activity
    matches = [table for table in known if _type_name(table) == activity]
    if len(matches) == 1:
        return matches[0]
    raise ObjectValueError(
        f"Unknown activity {activity!r}; event types are {', '.join(known)}."
        if not matches else f"Activity {activity!r} is ambiguous: {', '.join(matches)}."
    )


def _type_name(table: str) -> str:
    """``e_celonis_PostGoodsIssue`` -> ``PostGoodsIssue``: drop the lowercase namespace."""
    parts = table.split("_")
    while len(parts) > 1 and (parts[0].islower() or not parts[0]):
        parts.pop(0)
    return "_".join(parts)


@dataclass(frozen=True)
class ToOne(Generic[O]):
    """A to-one relationship of one object; ``fetch()`` requests the related object."""

    _collection: ObjectCollection[O]

    def fetch(self) -> O | None:
        items = self._collection._fetch(limit=2, offset=0)
        if len(items) > 1:
            raise ObjectIdentityError("A to-one relationship resolved to several objects.")
        return items[0] if items else None


@dataclass(frozen=True)
class ObjectPage(Generic[O]):
    """One page of objects in key order, with a way to request the next page."""

    items: tuple[O, ...]
    offset: int
    page_size: int
    has_more: bool
    _collection: ObjectCollection[O] = field(repr=False, compare=False)

    def __iter__(self) -> Iterator[O]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def next_page(self) -> ObjectPage[O] | None:
        """Fetch the following page, or return None when this is the last."""
        if not self.has_more:
            return None
        return self._collection.fetch_page(page_size=self.page_size, offset=self.offset + len(self.items))


@dataclass(frozen=True)
class ObjectCollection(Generic[O]):
    """An immutable, filterable set of one object type; fetches are explicit."""

    _session: KnowledgeModelClient
    _type: type[O]
    _predicates: tuple[Predicate, ...] = ()
    _order: tuple[Sort, ...] = ()
    _empty: bool = False

    @property
    def object_type(self) -> type[O]:
        return self._type

    def where(self, *predicates: Predicate) -> ObjectCollection[O]:
        """Return a narrower collection; all predicates must hold (AND)."""
        definition = self._type.fields
        for predicate in predicates:
            if not isinstance(predicate, Predicate):
                raise QueryValidationError(
                    "where() accepts field predicates such as Plant.fields.country.eq(...)."
                )
            if predicate.owner is not type(definition):
                raise QueryValidationError(
                    f"A predicate on {predicate.owner._object_type} cannot filter "
                    f"{definition.object_type} objects."
                )
        return replace(self, _predicates=(*self._predicates, *predicates))

    def order_by(self, *sorts: Sort | Operand[Any]) -> ObjectCollection[O]:
        """Replace the ordering by fields or aggregates (ascending unless
        ``.desc()``). The key breaks ties."""
        definition = self._type.fields
        order = []
        for sort in sorts:
            sort = sort.asc() if isinstance(sort, Operand) else sort
            if not isinstance(sort, Sort) or sort.field.owner is not type(definition):
                raise QueryValidationError(
                    f"order_by() accepts fields of {definition.object_type}, such as "
                    "Type.fields.name.asc()."
                )
            order.append(sort)
        return replace(self, _order=tuple(order))

    def get(self, key: Any) -> O:
        """Fetch one object by business key; composite keys are tuples."""
        definition = self._type.fields
        key_fields = definition.key_fields
        parts = (key,) if len(key_fields) == 1 else key
        if not isinstance(parts, tuple) or len(parts) != len(key_fields):
            raise QueryValidationError(
                f"{definition.object_type} keys have {len(key_fields)} parts: "
                f"{', '.join(f.name for f in key_fields)}."
            )
        if any(part is None for part in parts):
            raise QueryValidationError("Business keys cannot contain None.")
        items = self.where(*(f.eq(part) for f, part in zip(key_fields, parts)))._fetch(limit=2, offset=0)
        if not items:
            raise ObjectNotFoundError(f"No {definition.object_type} object has key {key!r}.")
        if len(items) > 1:
            raise ObjectIdentityError(f"Several {definition.object_type} objects have key {key!r}.")
        return items[0]

    def fetch_page(self, page_size: int = 100, *, offset: int = 0) -> ObjectPage[O]:
        """Fetch objects ordered by key. Offsets move with live data changes."""
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= MAX_PAGE_SIZE:
            raise QueryValidationError(f"page_size must be an integer from 1 to {MAX_PAGE_SIZE}.")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise QueryValidationError("offset must be a non-negative integer.")
        items = self._fetch(limit=page_size + 1, offset=offset)
        return ObjectPage(tuple(items[:page_size]), offset, page_size, len(items) > page_size, self)

    def _fetch(self, *, limit: int, offset: int) -> list[O]:
        if self._empty:
            return []
        return self._session._read(self._type, self._predicates, self._order, limit=limit, offset=offset)


@dataclass(frozen=True)
class ObjectModel:
    """Generated registry of object types captured from one Knowledge Model."""

    source: Source
    data_model_id: str | None
    variables: Mapping[str, str | None]
    """KM input variables (``${name}``) used by field expressions, with their
    data types. Every read binds the KM's current values."""
    objects: tuple[type[Object], ...]

    def __iter__(self) -> Iterator[type[Object]]:
        return iter(self.objects)

    def __len__(self) -> int:
        return len(self.objects)

    def __getitem__(self, object_type_id: str) -> type[Object]:
        """Look up a generated class by its captured record ID."""
        for object_type in self.objects:
            if object_type.fields.object_type == object_type_id:
                return object_type
        raise KeyError(object_type_id)
