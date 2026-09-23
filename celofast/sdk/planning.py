"""Private translation of object reads into KM export requests.

A read loads the key and every generated field, applies one filter built from
the predicate tree, and orders by the requested fields and then the key so
pages are deterministic. Applications never see the expressions produced here.

Every condition is rendered two-valued (``CASE WHEN ... THEN 1 ELSE 0 END``),
so ``~`` is an exact complement even when values are null. Relationship
predicates are resolved before rendering: ``resolve`` returns the distinct
linked values of the related objects that match, and the source field is then
tested for membership. They therefore follow the declared link mapping and do
not depend on Data Model joins.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone

from celofast.exceptions import QueryValidationError
from celofast.query import bind_variables
from celofast.sdk.definitions import (
    And,
    Comparison,
    Field,
    Not,
    ObjectDefinition,
    Or,
    Predicate,
    Related,
    Sort,
)

Resolver = Callable[[Related], Sequence[object]]
_ORDERING = {"lt": "<", "lte": "<=", "gt": ">", "gte": ">="}


def _literal(value: object) -> str:
    if isinstance(value, str):
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return repr(value)
    if isinstance(value, datetime):
        # PQL date constants have millisecond precision; never round silently.
        if value.microsecond % 1000:
            raise QueryValidationError("PQL datetimes require millisecond precision.")
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        delta = value - datetime(1970, 1, 1)
        milliseconds = (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000
        return f"{{t {milliseconds}}}"
    if isinstance(value, date):
        return "{d '" + value.isoformat() + "'}"
    raise QueryValidationError(f"Unsupported filter value {type(value).__name__}.")


@dataclass(frozen=True)
class ReadPlan:
    """Aliased columns, AND-combined filters, and (expression, ascending) order."""

    columns: tuple[tuple[str, str], ...]
    filters: tuple[str, ...]
    order_by: tuple[tuple[str, bool], ...]


class _Renderer:
    def __init__(self, variables: Mapping[str, str], resolve: Resolver) -> None:
        self.variables = variables
        self.resolve = resolve

    def expression(self, field: Field[object]) -> str:
        pql = field.metadata.get("pql")
        if not isinstance(pql, str) or not pql.strip():
            raise QueryValidationError(f"{field.owner}.{field.name} has no expression.")
        # A newline keeps a trailing line comment from consuming what follows.
        return f"({bind_variables(pql, self.variables)}\n)"

    def condition(self, predicate: Predicate, negate: bool = False) -> str:
        if isinstance(predicate, (And, Or)):
            # De Morgan keeps negation on two-valued atoms.
            joiner = " AND " if isinstance(predicate, And) != negate else " OR "
            return "(" + joiner.join(self.condition(p, negate) for p in predicate.parts) + ")"
        if isinstance(predicate, Not):
            return self.condition(predicate.part, not negate)
        indicator, negated = self.indicator(predicate)
        return f"{indicator} = {0 if negate != negated else 1}"

    def indicator(self, predicate: Predicate) -> tuple[str, bool]:
        """A 0/1 expression and whether the predicate is its complement."""
        if isinstance(predicate, Comparison):
            left = self.expression(predicate.field)
            op, operand = predicate.op, predicate.operand
            if operand is None:
                return f"ISNULL({left})", op == "ne"
            if isinstance(operand, Field):
                right = self.expression(operand)
                if op in ("eq", "ne"):
                    both_null = f"ISNULL({left}) = 1 AND ISNULL({right}) = 1"
                    return (
                        f"CASE WHEN {left} = {right} THEN 1 WHEN {both_null} THEN 1 ELSE 0 END",
                        op == "ne",
                    )
                return f"CASE WHEN {left} {_ORDERING[op]} {right} THEN 1 ELSE 0 END", False
            if op in ("eq", "ne"):
                return f"CASE WHEN {left} = {_literal(operand)} THEN 1 ELSE 0 END", op == "ne"
            return f"CASE WHEN {left} {_ORDERING[op]} {_literal(operand)} THEN 1 ELSE 0 END", False
        if isinstance(predicate, Related):
            values = [value for value in self.resolve(predicate) if value is not None]
            left = self.expression(predicate.source)
            if not values:
                # No related object matches: an always-false test on this column.
                return f"CASE WHEN ISNULL({left}) = 2 THEN 1 ELSE 0 END", False
            members = ", ".join(_literal(value) for value in values)
            return f"CASE WHEN {left} IN ({members}) THEN 1 ELSE 0 END", False
        raise QueryValidationError(f"Unsupported predicate {type(predicate).__name__}.")

    def filters(self, predicates: tuple[Predicate, ...]) -> tuple[str, ...]:
        return tuple(f"FILTER {self.condition(p)};" for p in predicates)


def plan_read(
    definition: ObjectDefinition,
    predicates: tuple[Predicate, ...],
    order: tuple[Sort, ...] = (),
    *,
    variables: Mapping[str, str],
    resolve: Resolver,
) -> ReadPlan:
    """Plan a complete-object read; unbound ``${name}`` placeholders fail here."""
    renderer = _Renderer(variables, resolve)
    columns = tuple(
        (f"f{index}", renderer.expression(field)) for index, field in enumerate(definition)
    )
    ordering = [(renderer.expression(sort.field), sort.ascending) for sort in order]
    ordering += [(renderer.expression(field), True) for field in definition.key_fields]
    return ReadPlan(columns, renderer.filters(predicates), tuple(ordering))


def plan_values(
    field: Field[object],
    predicate: Predicate | None,
    *,
    variables: Mapping[str, str],
    resolve: Resolver,
) -> ReadPlan:
    """Plan a read of the distinct values of one field among matching objects."""
    renderer = _Renderer(variables, resolve)
    return ReadPlan(
        columns=(("v", renderer.expression(field)),),
        filters=renderer.filters(() if predicate is None else (predicate,)),
        order_by=(),
    )
