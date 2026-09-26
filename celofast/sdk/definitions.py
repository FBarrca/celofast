"""Offline object definitions: fields, predicates, and what an object type is.

Definitions never hold values or connections. A generated ``PlantDefinition``
declares one ``Field`` per property; ``Plant.fields.country`` is that field,
while ``plant.country`` is always a loaded Python value. A field is scoped to
the definition class that declares it, so fields and predicates of different
types, packages, or reloads never mix.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal, TypeVar

from celofast.exceptions import ObjectValueError, QueryValidationError
from celofast.sdk.hydration import ValueType, filter_value

if TYPE_CHECKING:
    from celofast.sdk.objects import EventLogRelation, ObjectLinkRelation, Relation, ToManyRelation

T = TypeVar("T")
Operator = Literal["eq", "ne", "lt", "lte", "gt", "gte", "in", "between", "like"]
AggregateFunction = Literal["count", "count_distinct", "sum", "avg", "min", "max", "median"]
ProcessMode = Literal["contains", "starts_with", "ends_with", "excludes"]


class Operand(Generic[T]):
    """A value per object of one type: a field, or an aggregate over a relation.

    Comparisons follow Python semantics for None: eq/ne treat None as a value,
    and ordering with a null operand is false. ``~`` is an exact complement, so
    ``~x.eq(v)`` equals ``x.ne(v)``.
    """

    owner: type[ObjectDefinition]
    """The definition class of the object type this operand describes."""
    name: str
    value_type: ValueType
    nullable: bool

    def eq(self, other: T | Operand[Any]) -> Predicate:
        """Equal to a value or another operand; ``None`` matches nulls."""
        return self._compare("eq", other)

    def ne(self, other: T | Operand[Any]) -> Predicate:
        """Not equal to a value or another operand; nulls differ from values."""
        return self._compare("ne", other)

    def lt(self, other: T | Operand[Any]) -> Predicate:
        return self._compare("lt", other)

    def lte(self, other: T | Operand[Any]) -> Predicate:
        return self._compare("lte", other)

    def gt(self, other: T | Operand[Any]) -> Predicate:
        return self._compare("gt", other)

    def gte(self, other: T | Operand[Any]) -> Predicate:
        return self._compare("gte", other)

    def is_in(self, values: Iterable[T]) -> Predicate:
        """Equal to one of ``values`` (PQL ``IN``); a null never matches."""
        options = tuple(values)
        if not options:
            raise QueryValidationError("is_in() needs at least one value.")
        if any(value is None for value in options):
            raise ObjectValueError("is_in() values cannot be None; combine with eq(None).")
        return Comparison(self, "in", tuple(filter_value(self, value) for value in options))

    def between(self, low: T, high: T) -> Predicate:
        """Within ``low`` and ``high``, both inclusive (PQL ``BETWEEN``)."""
        if low is None or high is None:
            raise ObjectValueError("between() needs two values.")
        self._require_ordering()
        return Comparison(self, "between", (filter_value(self, low), filter_value(self, high)))

    def like(self, pattern: str) -> Predicate:
        """Matches a PQL ``LIKE`` pattern: ``%`` any text, ``_`` one character."""
        if self.value_type != "str":
            raise ObjectValueError(f"{self} is not a string value.")
        if not isinstance(pattern, str):
            raise ObjectValueError("like() needs a string pattern.")
        return Comparison(self, "like", pattern)

    def asc(self) -> Sort:
        return Sort(self, ascending=True)

    def desc(self) -> Sort:
        return Sort(self, ascending=False)

    def __str__(self) -> str:
        return f"{self.owner._object_type}.{self.name}"

    def _require_ordering(self) -> None:
        if self.value_type == "bool":
            raise ObjectValueError(f"{self} is boolean and has no ordering.")

    def _compare(self, op: Operator, other: object) -> Predicate:
        ordering = op not in ("eq", "ne")
        if isinstance(other, Operand):
            if other.owner is not self.owner:
                raise QueryValidationError(f"{self} can only be compared with values of the same type.")
            types = {self.value_type, other.value_type}
            if len(types) > 1 and not types <= {"int", "float"}:
                raise ObjectValueError(
                    f"Cannot compare {self.value_type} {self.name} with {other.value_type} {other.name}."
                )
        elif other is None and ordering:
            raise ObjectValueError(f"{op}() needs a value; nulls only support eq() and ne().")
        else:
            other = filter_value(self, other)
        if ordering:
            self._require_ordering()
        return Comparison(self, op, other)


class Field(Operand[T]):
    """A typed, queryable object property, declared on a generated definition.

    The field learns its name and owner from the class body that declares it;
    whether it is nullable follows from the owner's key.
    """

    def __init__(
        self,
        id: str,
        expression: str,
        value_type: ValueType,
        *,
        display_name: str | None = None,
        description: str | None = None,
    ) -> None:
        self.id = id
        """The captured attribute ID."""
        self.expression = expression
        self.value_type = value_type
        self.display_name = display_name
        self.description = description
        self.nullable = True

    def __set_name__(self, owner: type[ObjectDefinition], name: str) -> None:
        self.owner, self.name = owner, name

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self}, {self.value_type})"


class DateTimeField(Field[T]):
    """A datetime field; filters also accept a ``date``, meaning its midnight."""

    if TYPE_CHECKING:  # Only the accepted argument types differ.
        def eq(self, other: T | _dt.date | Operand[Any]) -> Predicate: ...
        def ne(self, other: T | _dt.date | Operand[Any]) -> Predicate: ...
        def lt(self, other: T | _dt.date | Operand[Any]) -> Predicate: ...
        def lte(self, other: T | _dt.date | Operand[Any]) -> Predicate: ...
        def gt(self, other: T | _dt.date | Operand[Any]) -> Predicate: ...
        def gte(self, other: T | _dt.date | Operand[Any]) -> Predicate: ...
        def is_in(self, values: Iterable[T | _dt.date]) -> Predicate: ...
        def between(self, low: T | _dt.date, high: T | _dt.date) -> Predicate: ...


class Aggregate(Operand[T]):
    """One value per source object, aggregated over its related objects.

    Built with ``Type.relations.<to_many>.count()``, ``.sum(field)``, and so on;
    compare it like a field. It is NULL when no related value exists, except
    ``count`` and ``count_distinct``, which are 0.
    """

    def __init__(
        self,
        relation: ToManyRelation[Any],
        function: AggregateFunction,
        field: Field[Any],
        predicate: Predicate | None,
    ) -> None:
        # ``field`` is the aggregated field of the related type (its key for ``count``).
        self.relation, self.function, self.field, self.predicate = relation, function, field, predicate
        counts = function in ("count", "count_distinct")
        self.owner = type(relation.source.fields)
        self.name = f"{relation.name}.{function}({'' if function == 'count' else field.name})"
        self.value_type = "int" if counts else "float" if function == "avg" else field.value_type
        self.nullable = not counts


@dataclass(frozen=True)
class Sort:
    """Ordering by a field or aggregate; the business key always breaks ties."""

    field: Operand[Any]
    ascending: bool = True


class Predicate:
    """A condition on one object type, composable with ``&``, ``|``, and ``~``."""

    @property
    def owner(self) -> type[ObjectDefinition]:
        """The definition class of the object type this predicate filters."""
        raise NotImplementedError

    def __and__(self, other: Predicate) -> Predicate:
        return And._of(self, other)

    def __or__(self, other: Predicate) -> Predicate:
        return Or._of(self, other)

    def __invert__(self) -> Predicate:
        return Not(self)

    def __bool__(self) -> bool:
        raise TypeError("Combine predicates with &, |, and ~; not with and/or/not.")


@dataclass(frozen=True, eq=False)
class Comparison(Predicate):
    """A field or aggregate compared with a value or another operand of the same type."""

    field: Operand[Any]
    op: Operator
    operand: object

    @property
    def owner(self) -> type[ObjectDefinition]:
        return self.field.owner


@dataclass(frozen=True, eq=False)
class _Group(Predicate):
    parts: tuple[Predicate, ...]

    @classmethod
    def _of(cls, *parts: Predicate) -> Predicate:
        flat: list[Predicate] = []
        for part in parts:
            if not isinstance(part, Predicate):
                raise QueryValidationError("Predicates combine only with other predicates.")
            flat.extend(part.parts if type(part) is cls else (part,))
        if len({p.owner for p in flat}) != 1:
            raise QueryValidationError(
                "Combined predicates must describe the same object type; "
                "use a relation (has/any) to reach related objects."
            )
        return cls(tuple(flat))

    @property
    def owner(self) -> type[ObjectDefinition]:
        return self.parts[0].owner


class And(_Group):
    """All parts hold."""


class Or(_Group):
    """At least one part holds."""


@dataclass(frozen=True, eq=False)
class Not(Predicate):
    """The exact complement of a predicate."""

    part: Predicate

    @property
    def owner(self) -> type[ObjectDefinition]:
        return self.part.owner


@dataclass(frozen=True, eq=False)
class Related(Predicate):
    """Some related object matches: ``relations.x.has(...)`` or ``.any(...)``.

    ``predicate`` is a condition on the related type, or None for "a related
    object exists".
    """

    relation: Relation[Any]
    predicate: Predicate | None

    @property
    def owner(self) -> type[ObjectDefinition]:
        return type(self.relation.source.fields)


@dataclass(frozen=True, eq=False)
class Linked(Predicate):
    """The object is at the other end of an Object Link from the object keyed ``key``.

    Built by traversal: ``plant.links.link_targets`` is the set of objects that
    ``plant`` links to.
    """

    relation: ObjectLinkRelation[Any]
    key: object

    @property
    def owner(self) -> type[ObjectDefinition]:
        return type(self.relation.target.fields)


@dataclass(frozen=True, eq=False)
class Process(Predicate):
    """A condition on the activities of an object's event log (``MATCH_ACTIVITIES``).

    Built with ``Type.relations.<log>.contains(...)`` and similar; it holds for
    the object whose history in that log matches ``mode``.
    """

    relation: EventLogRelation[Any]
    mode: ProcessMode
    activities: tuple[str, ...]

    @property
    def owner(self) -> type[ObjectDefinition]:
        return type(self.relation.source.fields)


class ObjectDefinition:
    """Describes one object type: its population, key, and fields.

    Generated subclasses declare ``Field`` members and the class-level facts
    below. Only ``object_type``, ``metadata``, and ``key_fields`` are public
    names, so business attributes keep natural names.
    """

    _object_type: ClassVar[str]
    _table: ClassVar[str | None] = None
    _key: ClassVar[tuple[str, ...]] = ()
    _metadata: ClassVar[Mapping[str, str | None]] = {}
    _members: ClassVar[tuple[str, ...]] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._members = tuple(name for name, value in vars(cls).items() if isinstance(value, Field))
        for name in cls._members:
            getattr(cls, name).nullable = name not in cls._key

    @property
    def object_type(self) -> str:
        """The captured record ID; never an instance's business key."""
        return self._object_type

    @property
    def metadata(self) -> Mapping[str, str | None]:
        """The record's captured ``displayName`` and ``description``."""
        return self._metadata

    @property
    def key_fields(self) -> tuple[Field[Any], ...]:
        """Fields whose values together form each instance's business key."""
        return tuple(getattr(self, name) for name in self._key)

    @property
    def _default_order(self) -> tuple[Field[Any], ...]:
        """Fields that order reads after any requested sort; they must identify rows."""
        return self.key_fields

    def __iter__(self) -> Iterator[Field[Any]]:
        """Iterate all loaded fields in generated order."""
        return (getattr(self, name) for name in self._members)

    def __len__(self) -> int:
        return len(self._members)

    def __getitem__(self, attribute_id: str) -> Field[Any]:
        """Look up a field by its exact captured attribute ID."""
        for field in self:
            if field.id == attribute_id:
                return field
        raise KeyError(attribute_id)


class EventDefinition(ObjectDefinition):
    """Describes one event log: the events of its lead object, one row per event.

    Generated subclasses always declare the role fields ``case`` (the lead
    object's key), ``event_id``, ``activity`` (the event type), and
    ``timestamp``. Rows are identified by ``case`` and ``event_id``, because
    one event can belong to several lead objects, and read in time order.
    """

    _event_types: ClassVar[tuple[str, ...]] = ()
    """The Data Model's event type tables at pull; activities name one of them."""

    @property
    def _default_order(self) -> tuple[Field[Any], ...]:
        timestamp: Field[Any] = getattr(self, "timestamp")
        return (timestamp, *(field for field in self.key_fields if field is not timestamp))
