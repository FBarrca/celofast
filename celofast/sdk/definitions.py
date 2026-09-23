"""Offline object definitions: what an object type is and which fields it has.

Definitions never hold values or connections. Generated value classes expose
them as ``Plant.fields``; ``plant.country`` is always a loaded Python value.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Generic, Literal, TypeVar

from celofast.exceptions import ObjectValueError, QueryValidationError
from celofast.sdk.capture import Capture
from celofast.sdk.hydration import ValueType, check_filter_value

T = TypeVar("T")
Path = tuple[str | int, ...]


@dataclass(frozen=True)
class Definition:
    """A captured definition addressed by its path in one capture."""

    capture: Capture
    path: Path = ()

    @property
    def metadata(self) -> Mapping[str, Any]:
        """Immutable captured metadata, including fields without generated names."""
        value: Any = self.capture.definition
        for segment in self.path:
            if isinstance(value, tuple) and isinstance(segment, str):
                matches = [
                    item
                    for item in value
                    if isinstance(item, Mapping) and item.get("id") == segment
                ]
                if len(matches) != 1:
                    raise KeyError(segment)
                value = matches[0]
            else:
                value = value[segment]
        return value


@dataclass(frozen=True, kw_only=True)
class Field(Definition, Generic[T]):
    """A typed, queryable object property. Values live on loaded objects."""

    name: str
    owner: str
    value_type: ValueType
    nullable: bool = True

    @property
    def id(self) -> str | None:
        """The captured attribute ID."""
        return self.metadata.get("id")

    @property
    def display_name(self) -> str | None:
        return self.metadata.get("displayName")

    @property
    def description(self) -> str | None:
        return self.metadata.get("description")

    # Comparisons follow Python semantics for None: eq/ne treat None as a
    # value, and ordering with a null operand is false. ``~`` is an exact
    # complement, so ``~f.eq(x)`` equals ``f.ne(x)``.
    def eq(self, other: T | Field[Any]) -> Predicate:
        """Equal to a value or another field; ``None`` matches nulls."""
        return self._compare("eq", other)

    def ne(self, other: T | Field[Any]) -> Predicate:
        """Not equal to a value or another field; nulls differ from values."""
        return self._compare("ne", other)

    def lt(self, other: T | Field[Any]) -> Predicate:
        return self._compare("lt", other)

    def lte(self, other: T | Field[Any]) -> Predicate:
        return self._compare("lte", other)

    def gt(self, other: T | Field[Any]) -> Predicate:
        return self._compare("gt", other)

    def gte(self, other: T | Field[Any]) -> Predicate:
        return self._compare("gte", other)

    def asc(self) -> Sort:
        return Sort(self, ascending=True)

    def desc(self) -> Sort:
        return Sort(self, ascending=False)

    def _compare(self, op: Operator, other: object) -> Predicate:
        ordering = op not in ("eq", "ne")
        if isinstance(other, Field):
            if other.owner != self.owner or other.capture is not self.capture:
                raise QueryValidationError(
                    f"{self.owner}.{self.name} can only be compared with fields of the same type."
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


Operator = Literal["eq", "ne", "lt", "lte", "gt", "gte"]


@dataclass(frozen=True)
class Sort:
    """Ordering by one field; the business key always breaks ties."""

    field: Field[Any]
    ascending: bool = True


class Predicate:
    """A condition on one object type, composable with ``&``, ``|``, and ``~``."""

    @property
    def owner(self) -> str:
        raise NotImplementedError

    @property
    def capture(self) -> Capture:
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
    """A field compared with a value or with another field of the same type."""

    field: Field[Any]
    op: Operator
    operand: object

    @property
    def owner(self) -> str:
        return self.field.owner

    @property
    def capture(self) -> Capture:
        return self.field.capture


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
        if len({(p.owner, id(p.capture)) for p in flat}) != 1:
            raise QueryValidationError(
                "Combined predicates must describe the same object type; "
                "use a relation (has/any) to reach related objects."
            )
        return cls(tuple(flat))

    @property
    def owner(self) -> str:
        return self.parts[0].owner

    @property
    def capture(self) -> Capture:
        return self.parts[0].capture


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
    def capture(self) -> Capture:
        return self.part.capture


@dataclass(frozen=True, eq=False)
class Related(Predicate):
    """Some related object matches: ``relations.x.has(...)`` or ``.any(...)``.

    ``source`` and ``target`` are the single linked fields; ``predicate`` is a
    condition on the related type, or None for "has any related object".
    """

    link: str
    source: Field[Any]
    target: Field[Any]
    predicate: Predicate | None

    @property
    def owner(self) -> str:
        return self.source.owner

    @property
    def capture(self) -> Capture:
        return self.source.capture


@dataclass(frozen=True, kw_only=True)
class LinkDefinition:
    """A declared relationship: target type, cardinality, and field mapping."""

    name: str
    target: str
    cardinality: Literal["one", "many"]
    on: tuple[tuple[str, str], ...]
    """Pairs of (source field name, target field name)."""


@dataclass(frozen=True, kw_only=True)
class ObjectDefinition(Definition):
    """Describes one object type: its population, key, fields, and links.

    Only ``object_type``, ``metadata``, ``key_fields``, ``links``, ``capture``,
    and ``path`` are reserved, so business attributes keep natural names.
    Display names and descriptions are in ``metadata``.
    """

    # Generated subclasses declare fields and set these class-level facts.
    _members: ClassVar[tuple[str, ...]] = ()
    _key: ClassVar[tuple[str, ...]] = ()
    _links: ClassVar[tuple[LinkDefinition, ...]] = ()

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
        return str(self.metadata.get("id"))

    @property
    def key_fields(self) -> tuple[Field[Any], ...]:
        """Fields whose values together form each instance's business key."""
        return tuple(getattr(self, name) for name in self._key)

    @property
    def links(self) -> Mapping[str, LinkDefinition]:
        """Declared relationships by generated accessor name."""
        return {link.name: link for link in self._links}
