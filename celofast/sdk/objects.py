"""Loaded business objects, typed collections, and explicit relationship reads.

Instances are immutable snapshots: reading ``plant.country`` never performs a
request. Only collection and relationship fetches contact Celonis, through the
client that loaded the instance.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Protocol, TypeVar

from celofast.exceptions import (
    ObjectIdentityError,
    ObjectNotFoundError,
    QueryValidationError,
)
from celofast.sdk.capture import Source
from celofast.sdk.definitions import (
    Field,
    LinkDefinition,
    ModelInfo,
    ObjectDefinition,
    Predicate,
    Related,
    Sort,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

O = TypeVar("O", bound="Object")
MAX_PAGE_SIZE = 10_000


class _Session(Protocol):
    """The private runtime that retrieves objects for one connected client."""

    @property
    def model(self) -> ObjectModel: ...

    def objects(self, object_type: type[O]) -> ObjectCollection[O]: ...

    def _read(
        self,
        object_type: type[O],
        predicates: tuple[Predicate, ...],
        order: tuple[Sort, ...],
        *,
        limit: int,
        offset: int,
    ) -> list[O]: ...


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
        if len(link.on) != 1:
            raise QueryValidationError(
                f"Relation {self.name!r} maps several fields; relationship predicates "
                "support single-field links."
            )
        target = self.target.fields
        if predicate is not None and (
            predicate.owner != target.object_type or predicate.model is not target.model
        ):
            raise QueryValidationError(
                f"{self.name} relates to {target.object_type}; the predicate describes "
                f"{predicate.owner}."
            )
        left, right = link.on[0]
        return Related(
            link=self.name,
            source=getattr(self.source.fields, left),
            target=getattr(target, right),
            predicate=predicate,
        )


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
    _context: ClassVar[_Session | None] = None

    def _attach(self: O, context: _Session) -> O:
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

    def _session(self) -> _Session:
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

    _session: _Session
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

    def order_by(self, *sorts: Sort | Field[Any]) -> ObjectCollection[O]:
        """Replace the ordering; fields sort ascending. The key breaks ties."""
        definition = self._type.fields
        order = []
        for sort in sorts:
            sort = sort.asc() if isinstance(sort, Field) else sort
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


_REMOVED = frozenset({"KnowledgeModel", "KnowledgeObject", "Record", "Attribute", "KPI", "Filter", "Namespace", "Sort"})


def __getattr__(name: str) -> Any:
    # Packages generated for the removed query runtime import these names
    # before their version check runs; fail with the regeneration message.
    if name in _REMOVED:
        from celofast.sdk.loading import SDKCompatibilityError

        raise SDKCompatibilityError(
            f"{name} was removed with the KM query API. Generated KM packages now "
            "contain object classes; rerun celofast km pull and restart Python."
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
