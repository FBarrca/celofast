"""Offline object definitions: what an object type is and which fields it has.

Definitions never hold values or connections. Generated value classes expose
them as ``Plant.fields``; ``plant.country`` is always a loaded Python value.
Generated packages write every definition as Python literals; nothing is read
from data files at import.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Generic, Literal, TypeVar

from celofast.exceptions import ObjectValueError, QueryValidationError
from celofast.sdk.capture import Source
from celofast.sdk.hydration import ValueType, check_filter_value

T = TypeVar("T")


@dataclass(frozen=True, eq=False)
class ModelInfo:
    """The Knowledge Model one generated package was pulled from.

    One instance exists per generated package; definitions compare it by
    identity, so types from different packages (or reloads) never mix.
    """

    source: Source
    data_model_id: str | None
    variables: tuple[str, ...] = ()
    """``${name}`` placeholders used by generated field expressions."""


class Operand(Generic[T]):
    """A value per object of one type: a field, or an aggregate over a relation.

    Comparisons follow Python semantics for None: eq/ne treat None as a value,
    and ordering with a null operand is false. ``~`` is an exact complement, so
    ``~x.eq(v)`` equals ``x.ne(v)``.
    """

    # Provided by subclasses.
    model: ModelInfo
    owner: str
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
        for value in options:
            if value is None:
                raise ObjectValueError("is_in() values cannot be None; combine with eq(None).")
            check_filter_value(self, value)
        return Comparison(self, "in", options)

    def between(self, low: T, high: T) -> Predicate:
        """Within ``low`` and ``high``, both inclusive (PQL ``BETWEEN``)."""
        if low is None or high is None:
            raise ObjectValueError("between() needs two values.")
        if self.value_type == "bool":
            raise ObjectValueError(f"{self.owner}.{self.name} is boolean and has no ordering.")
        check_filter_value(self, low)
        check_filter_value(self, high)
        return Comparison(self, "between", (low, high))

    def like(self, pattern: str) -> Predicate:
        """Matches a PQL ``LIKE`` pattern: ``%`` any text, ``_`` one character."""
        if self.value_type != "str":
            raise ObjectValueError(f"{self.owner}.{self.name} is not a string value.")
        if not isinstance(pattern, str):
            raise ObjectValueError("like() needs a string pattern.")
        return Comparison(self, "like", pattern)

    def asc(self) -> Sort:
        return Sort(self, ascending=True)

    def desc(self) -> Sort:
        return Sort(self, ascending=False)

    def _compare(self, op: Operator, other: object) -> Predicate:
        ordering = op not in ("eq", "ne")
        if isinstance(other, Operand):
            if other.owner != self.owner or other.model is not self.model:
                raise QueryValidationError(
                    f"{self.owner}.{self.name} can only be compared with values of the same type."
                )
            types = {self.value_type, other.value_type}
            if len(types) > 1 and not types <= {"int", "float"}:
                raise ObjectValueError(
                    f"Cannot compare {self.value_type} {self.name} with "
                    f"{other.value_type} {other.name}."
                )
        elif other is None and ordering:
            raise ObjectValueError(f"{op}() needs a value; nulls only support eq() and ne().")
        else:
            check_filter_value(self, other)
        if ordering and self.value_type == "bool":
            raise ObjectValueError(f"{self.owner}.{self.name} is boolean and has no ordering.")
        return Comparison(self, op, other)


@dataclass(frozen=True, kw_only=True)
class Field(Operand[T]):
    """A typed, queryable object property. Values live on loaded objects."""

    model: ModelInfo
    owner: str
    name: str
    id: str
    """The captured attribute ID."""
    expression: str
    value_type: ValueType
    nullable: bool = True
    display_name: str | None = None
    description: str | None = None


AggregateFunction = Literal["count", "count_distinct", "sum", "avg", "min", "max", "median"]


@dataclass(frozen=True, kw_only=True, eq=False)
class Aggregate(Operand[T]):
    """One value per source object, aggregated over its related objects.

    Built with ``Type.relations.<to_many>.count()``, ``.sum(field)``, and so on;
    compare it like a field. It is NULL when no related value exists, except
    ``count`` and ``count_distinct``, which are 0.
    """

    model: ModelInfo
    owner: str
    name: str
    value_type: ValueType
    nullable: bool
    function: AggregateFunction
    link: LinkDefinition
    source: ObjectDefinition
    target: ObjectDefinition
    field: Field[Any]
    """The aggregated field of the related type (its key for ``count``)."""
    predicate: Predicate | None


Operator = Literal["eq", "ne", "lt", "lte", "gt", "gte", "in", "between", "like"]


@dataclass(frozen=True)
class Sort:
    """Ordering by a field or aggregate; the business key always breaks ties."""

    field: Operand[Any]
    ascending: bool = True


class Predicate:
    """A condition on one object type, composable with ``&``, ``|``, and ``~``."""

    @property
    def owner(self) -> str:
        raise NotImplementedError

    @property
    def model(self) -> ModelInfo:
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
    def owner(self) -> str:
        return self.field.owner

    @property
    def model(self) -> ModelInfo:
        return self.field.model


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
        if len({(p.owner, id(p.model)) for p in flat}) != 1:
            raise QueryValidationError(
                "Combined predicates must describe the same object type; "
                "use a relation (has/any) to reach related objects."
            )
        return cls(tuple(flat))

    @property
    def owner(self) -> str:
        return self.parts[0].owner

    @property
    def model(self) -> ModelInfo:
        return self.parts[0].model


class And(_Group):
    """All parts hold."""


class Or(_Group):
    """At least one part holds."""


@dataclass(frozen=True, eq=False)
class Not(Predicate):
    """The exact complement of a predicate."""

    part: Predicate

    @property
    def owner(self) -> str:
        return self.part.owner

    @property
    def model(self) -> ModelInfo:
        return self.part.model


@dataclass(frozen=True, eq=False)
class Related(Predicate):
    """Some related object matches: ``relations.x.has(...)`` or ``.any(...)``.

    ``source`` and ``target`` are the two type definitions, ``link`` declares
    how they join, and ``predicate`` is a condition on the target type, or None
    for "a related object exists".
    """

    link: LinkDefinition
    source: ObjectDefinition
    target: ObjectDefinition
    predicate: Predicate | None

    @property
    def owner(self) -> str:
        return self.source.object_type

    @property
    def model(self) -> ModelInfo:
        return self.source.model


@dataclass(frozen=True, kw_only=True)
class LinkDefinition:
    """A declared relationship: target type, cardinality, and field mapping."""

    name: str
    target: str
    cardinality: Literal["one", "many"]
    on: tuple[tuple[str, str], ...]
    """Pairs of (source field name, target field name)."""
    join: Literal["fk", "lookup"] | None = None
    """How predicates reach the target: a Data Model foreign key, a PQL LOOKUP,
    or None when the link only supports traversal."""


@dataclass(frozen=True, kw_only=True)
class ObjectDefinition:
    """Describes one object type: its population, key, fields, and links.

    Only ``model``, ``object_type``, ``metadata``, ``key_fields``, and
    ``links`` are reserved, so business attributes keep natural names. The
    record's display name and description are in ``metadata``.
    """

    # Generated subclasses declare Field members and set these class-level facts.
    _model: ClassVar[ModelInfo]
    _object_type: ClassVar[str]
    _table: ClassVar[str | None] = None
    _metadata: ClassVar[Mapping[str, str | None]] = {}
    _members: ClassVar[tuple[str, ...]] = ()
    _key: ClassVar[tuple[str, ...]] = ()
    _links: ClassVar[tuple[LinkDefinition, ...]] = ()

    @property
    def model(self) -> ModelInfo:
        """The Knowledge Model this type was generated from."""
        return self._model

    @property
    def metadata(self) -> Mapping[str, str | None]:
        """The record's captured ``displayName`` and ``description``."""
        return self._metadata

    def __iter__(self) -> Iterator[Field[Any]]:
        """Iterate all loaded fields in generated order."""
        for name in self._members:
            yield getattr(self, name)

    def __len__(self) -> int:
        return len(self._members)

    def __getitem__(self, attribute_id: str) -> Field[Any]:
        """Look up a field by its exact captured attribute ID."""
        matches = [field for field in self if field.id == attribute_id]
        if len(matches) != 1:
            raise KeyError(attribute_id)
        return matches[0]

    @property
    def object_type(self) -> str:
        """The captured record ID; never an instance's business key."""
        return self._object_type

    @property
    def key_fields(self) -> tuple[Field[Any], ...]:
        """Fields whose values together form each instance's business key."""
        return tuple(getattr(self, name) for name in self._key)

    @property
    def links(self) -> Mapping[str, LinkDefinition]:
        """Declared relationships by generated accessor name."""
        return {link.name: link for link in self._links}
