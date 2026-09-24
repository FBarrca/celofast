"""Loaded business objects, typed collections, and explicit relationship reads.

Instances are immutable snapshots: reading ``plant.country`` never performs a
request. Only collection and relationship fetches contact Celonis, through the
client that loaded the instance.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar

from celofast.exceptions import (
    ObjectValueError,
    ObjectIdentityError,
    ObjectNotFoundError,
    QueryValidationError,
)
from celofast.sdk.capture import Source
from celofast.sdk.hydration import ValueType
from celofast.sdk.definitions import (
    Aggregate,
    AggregateFunction,
    Field,
    LinkDefinition,
    ModelInfo,
    ObjectDefinition,
    Operand,
    Predicate,
    Related,
    Sort,
)

if TYPE_CHECKING:
    from celofast.resources.knowledge_model import KnowledgeModelClient

O = TypeVar("O", bound="Object")
T = TypeVar("T")
MAX_PAGE_SIZE = 10_000


@dataclass(frozen=True)
class ObjectRef:
    """A stable reference: KM source, object type ID, and business key."""

    source: Source
    object_type: str
    key: Any


@dataclass(frozen=True)
class _Relation(Generic[O]):
    name: str
    source: type[Object]
    target: type[O]

    def _related(self, predicate: Predicate | None) -> Predicate:
        link = self.source.fields.links[self.name]
        if link.join is None:
            raise QueryValidationError(
                f"Relation {self.name!r} has no Data Model foreign key or lookup path; "
                "use links for traversal instead."
            )
        target = self.target.fields
        if predicate is not None and (
            predicate.owner != target.object_type or predicate.model is not target.model
        ):
            raise QueryValidationError(
                f"{self.name} relates to {target.object_type}; the predicate describes "
                f"{predicate.owner}."
            )
        return Related(link=link, source=self.source.fields, target=target, predicate=predicate)


class ToOneRelation(_Relation[O]):
    """A to-one relationship used in predicates on the source type."""

    def has(self, predicate: Predicate | None = None) -> Predicate:
        """The related object exists and, if given, matches ``predicate``."""
        return self._related(predicate)


class ToManyRelation(_Relation[O]):
    """A to-many relationship used in predicates on the source type."""

    def any(self, predicate: Predicate | None = None) -> Predicate:
        """At least one related object exists and, if given, matches ``predicate``."""
        return self._related(predicate)

    # Aggregates compile to Pull-Up functions (PU_COUNT, PU_SUM, ...) on the
    # source table. ``predicate`` limits which related objects count. Results
    # are NULL when no related value exists, except the two counts (0).
    def count(self, predicate: Predicate | None = None) -> Aggregate[int]:
        """Number of related objects (PU_COUNT)."""
        return self._aggregate("count", None, predicate)

    def count_distinct(
        self, field: Field[Any], predicate: Predicate | None = None
    ) -> Aggregate[int]:
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
        link = self.source.fields.links[self.name]
        if link.join != "fk":
            raise QueryValidationError(
                f"Relation {self.name!r} has no Data Model foreign key; Pull-Up "
                "aggregates need one."
            )
        self._related(predicate)  # Validates the predicate's type.
        target = self.target.fields
        if field is None:
            field = target.key_fields[0]
        elif field.owner != target.object_type or field.model is not target.model:
            raise QueryValidationError(
                f"{function}() aggregates fields of {target.object_type}, not {field.owner}."
            )
        numeric = field.value_type in ("int", "float")
        if function in ("sum", "avg", "median") and not numeric:
            raise ObjectValueError(f"{function}() needs a numeric field; {field.name} is {field.value_type}.")
        if function in ("min", "max") and field.value_type == "bool":
            raise ObjectValueError(f"{function}() needs an ordered field; {field.name} is boolean.")
        value_type: ValueType = (
            "int" if function in ("count", "count_distinct")
            else "float" if function == "avg"
            else field.value_type
        )
        return Aggregate(
            model=self.source.fields.model,
            owner=self.source.fields.object_type,
            name=f"{self.name}.{function}({'' if function == 'count' else field.name})",
            value_type=value_type,
            nullable=function not in ("count", "count_distinct"),
            function=function,
            link=link,
            source=self.source.fields,
            target=target,
            field=field,
            predicate=predicate,
        )


class Relations:
    """Class-level relationship predicates; generated classes add typed accessors."""

    __slots__ = ()

    def _one(self, name: str, source: type[Object], target: type[O]) -> ToOneRelation[O]:
        return ToOneRelation(name, source, target)

    def _many(self, name: str, source: type[Object], target: type[O]) -> ToManyRelation[O]:
        return ToManyRelation(name, source, target)


@dataclass(frozen=True, kw_only=True)
class Object:
    """Base for generated value classes; each instance is one loaded object."""

    fields: ClassVar[ObjectDefinition]
    relations: ClassVar[Relations] = Relations()
    # The loading client is attached per instance but is not a dataclass
    # field, so equality, repr, and dataclasses.asdict() see only values.
    _context: ClassVar[KnowledgeModelClient | None] = None

    def _attach(self: O, context: KnowledgeModelClient) -> O:
        object.__setattr__(self, "_context", context)
        return self

    @property
    def ref(self) -> ObjectRef:
        definition = type(self).fields
        return ObjectRef(
            source=definition.model.source,
            object_type=definition.object_type,
            key=getattr(self, "key"),
        )

    @property
    def links(self) -> Links:
        """Typed relationship accessors; generated classes narrow this type."""
        return Links(self)


class Links:
    """Explicit relationship operations for one loaded object."""

    __slots__ = ("_owner",)

    def __init__(self, owner: Object) -> None:
        self._owner = owner

    def _definition(self, name: str) -> LinkDefinition:
        return type(self._owner).fields.links[name]

    def _session(self) -> KnowledgeModelClient:
        session = self._owner._context
        if session is None:
            raise QueryValidationError(
                "This object was not loaded by a client; relationships cannot be fetched."
            )
        return session

    def _collection(self, name: str, target: type[O]) -> ObjectCollection[O]:
        link = self._definition(name)
        if target.fields.object_type != link.target:
            raise QueryValidationError(f"Link {name!r} targets {link.target!r}.")
        collection = self._session().objects(target)
        values = [
            (getattr(target.fields, right), getattr(self._owner, left))
            for left, right in link.on
        ]
        if any(value is None for _, value in values):
            # A null reference identifies no related objects; skip the request.
            return replace(collection, _empty=True)
        return collection.where(*(field_.eq(value) for field_, value in values))

    def _many(self, name: str, target: type[O]) -> ObjectCollection[O]:
        return self._collection(name, target)

    def _one(self, name: str, target: type[O]) -> ToOne[O]:
        return ToOne(self._collection(name, target))


@dataclass(frozen=True)
class ToOne(Generic[O]):
    """A to-one relationship; ``fetch()`` requests the related object."""

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
        return self._collection.fetch_page(
            page_size=self.page_size, offset=self.offset + len(self.items)
        )


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
            if (
                predicate.owner != definition.object_type
                or predicate.model is not definition.model
            ):
                raise QueryValidationError(
                    f"A predicate on {predicate.owner} cannot filter "
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
            if not isinstance(sort, Sort) or sort.field.owner != definition.object_type or (
                sort.field.model is not definition.model
            ):
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
        matching = self.where(*(f.eq(part) for f, part in zip(key_fields, parts)))
        items = matching._fetch(limit=2, offset=0)
        if not items:
            raise ObjectNotFoundError(f"No {definition.object_type} object has key {key!r}.")
        if len(items) > 1:
            raise ObjectIdentityError(f"Several {definition.object_type} objects have key {key!r}.")
        return items[0]

    def fetch_page(self, page_size: int = 100, *, offset: int = 0) -> ObjectPage[O]:
        """Fetch objects ordered by key. Offsets move with live data changes."""
        if (
            isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or not 1 <= page_size <= MAX_PAGE_SIZE
        ):
            raise QueryValidationError(f"page_size must be an integer from 1 to {MAX_PAGE_SIZE}.")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise QueryValidationError("offset must be a non-negative integer.")
        items = self._fetch(limit=page_size + 1, offset=offset)
        return ObjectPage(
            items=tuple(items[:page_size]),
            offset=offset,
            page_size=page_size,
            has_more=len(items) > page_size,
            _collection=self,
        )

    def _fetch(self, *, limit: int, offset: int) -> list[O]:
        if self._empty:
            return []
        return self._session._read(
            self._type, self._predicates, self._order, limit=limit, offset=offset
        )


@dataclass(frozen=True)
class ObjectModel:
    """Generated registry of object types captured from one Knowledge Model."""

    info: ModelInfo
    objects: tuple[type[Object], ...]

    @property
    def source(self) -> Source:
        return self.info.source

    @property
    def data_model_id(self) -> str | None:
        return self.info.data_model_id

    @property
    def variables(self) -> tuple[str, ...]:
        """KM input variables (``${name}``) used by generated field expressions.

        Bind them with ``cf.km(model, variables={...})``.
        """
        return self.info.variables

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
