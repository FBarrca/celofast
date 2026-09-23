"""Private translation of object reads into a single KM export request.

A read loads the key and every generated field, applies one filter built from
the predicate tree, and orders by the requested fields and then the key so
pages are deterministic. Applications never see the expressions produced here.

Every condition is rendered two-valued (``CASE WHEN ... THEN 1 ELSE 0 END``),
so ``~`` is an exact complement even when values are null.

Relationship predicates are rendered in the same query:

* to-one ``has()`` pulls the related type's expressions onto the filtered row
  with ``BIND`` (Data Model foreign key) or ``LOOKUP`` (value join without a
  join path), so unmatched rows see NULL;
* to-many ``any()`` counts matching related rows with ``PU_COUNT`` on the
  filtered row's table, rendering the nested condition on the related table.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
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

_ORDERING = {"lt": "<", "lte": "<=", "gt": ">", "gte": ">="}

# Moves an expression of one object type onto the table being filtered.
Pull = Callable[[str], str]


def _identity(expression: str) -> str:
    return expression


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


def _table(definition: ObjectDefinition) -> str:
    if definition._table is None:
        raise QueryValidationError(
            f"{definition.object_type} is not a plain Data Model table; it cannot be joined."
        )
    return f'"{definition._table}"'


@dataclass(frozen=True)
class ReadPlan:
    """Aliased columns, AND-combined filters, and (expression, ascending) order."""

    columns: tuple[tuple[str, str], ...]
    filters: tuple[str, ...]
    order_by: tuple[tuple[str, bool], ...]


class _Renderer:
    def __init__(self, variables: Mapping[str, str]) -> None:
        self.variables = variables

    def expression(self, field: Field[object], pull: Pull = _identity) -> str:
        # A newline keeps a trailing line comment from consuming what follows.
        return pull(f"({bind_variables(field.expression, self.variables)}\n)")

    def condition(self, predicate: Predicate, pull: Pull = _identity, negate: bool = False) -> str:
        if isinstance(predicate, (And, Or)):
            # De Morgan keeps negation on two-valued atoms.
            joiner = " AND " if isinstance(predicate, And) != negate else " OR "
            parts = (self.condition(p, pull, negate) for p in predicate.parts)
            return "(" + joiner.join(parts) + ")"
        if isinstance(predicate, Not):
            return self.condition(predicate.part, pull, not negate)
        indicator, negated = self.indicator(predicate, pull)
        return f"{indicator} = {0 if negate != negated else 1}"

    def indicator(self, predicate: Predicate, pull: Pull) -> tuple[str, bool]:
        """A 0/1 expression and whether the predicate is its complement."""
        if isinstance(predicate, Comparison):
            return self.comparison(predicate, pull)
        if isinstance(predicate, Related):
            return self.related(predicate, pull), False
        raise QueryValidationError(f"Unsupported predicate {type(predicate).__name__}.")

    def comparison(self, predicate: Comparison, pull: Pull) -> tuple[str, bool]:
        left = self.expression(predicate.field, pull)
        op, operand = predicate.op, predicate.operand

        def case(test: str) -> str:
            return f"CASE WHEN {test} THEN 1 ELSE 0 END"

        if op == "in":
            assert isinstance(operand, tuple)
            members = ", ".join(_literal(value) for value in operand)
            return case(f"{left} IN ({members})"), False
        if op == "between":
            assert isinstance(operand, tuple)
            low, high = operand
            return case(f"{left} BETWEEN {_literal(low)} AND {_literal(high)}"), False
        if op == "like":
            return case(f"{left} LIKE {_literal(operand)}"), False
        if operand is None:
            return case(f"{left} IS NULL"), op == "ne"
        if isinstance(operand, Field):
            right = self.expression(operand, pull)
            if op in ("eq", "ne"):
                both_null = f"{left} IS NULL AND {right} IS NULL"
                return (
                    f"CASE WHEN {left} = {right} THEN 1 WHEN {both_null} THEN 1 ELSE 0 END",
                    op == "ne",
                )
            return case(f"{left} {_ORDERING[op]} {right}"), False
        if op in ("eq", "ne"):
            return case(f"{left} = {_literal(operand)}"), op == "ne"
        return case(f"{left} {_ORDERING[op]} {_literal(operand)}"), False

    def related(self, related: Related, pull: Pull) -> str:
        source, target, link = related.source, related.target, related.link
        if link.cardinality == "one":
            reach = self._reach(related)
            to_target: Pull = lambda expression: pull(reach(expression))  # noqa: E731
            exists = f"{self.expression(target.key_fields[0], to_target)} IS NOT NULL"
            if related.predicate is None:
                return f"CASE WHEN {exists} THEN 1 ELSE 0 END"
            inner = self.condition(related.predicate, to_target)
            return f"CASE WHEN {exists} AND {inner} THEN 1 ELSE 0 END"
        # To-many: count related rows on the source table. The nested
        # condition is evaluated on the related table itself.
        filter_ = (
            "" if related.predicate is None
            else f", {self.condition(related.predicate, _identity)}"
        )
        key = self.expression(target.key_fields[0])
        count = pull(f"PU_COUNT({_table(source)}, {key}{filter_})")
        return f"CASE WHEN {count} > 0 THEN 1 ELSE 0 END"

    def _reach(self, related: Related) -> Pull:
        """Moves a target expression onto the source row of a to-one link."""
        source, target, link = related.source, related.target, related.link
        table = _table(source)
        if link.join == "fk":
            return lambda expression: f"BIND({table}, {expression})"
        (left, right), = link.on  # Lookup links join on the single target key.
        condition = (
            f"({self.expression(getattr(source, left))}, "
            f"{self.expression(getattr(target, right))})"
        )
        return lambda expression: f"LOOKUP({table}, {expression}, {condition})"

    def filters(self, predicates: tuple[Predicate, ...]) -> tuple[str, ...]:
        return tuple(f"FILTER {self.condition(p)};" for p in predicates)


def plan_read(
    definition: ObjectDefinition,
    predicates: tuple[Predicate, ...],
    order: tuple[Sort, ...] = (),
    *,
    variables: Mapping[str, str],
) -> ReadPlan:
    """Plan a complete-object read; unbound ``${name}`` placeholders fail here."""
    renderer = _Renderer(variables)
    columns = tuple(
        (f"f{index}", renderer.expression(field)) for index, field in enumerate(definition)
    )
    ordering = [(renderer.expression(sort.field), sort.ascending) for sort in order]
    ordering += [(renderer.expression(field), True) for field in definition.key_fields]
    return ReadPlan(columns, renderer.filters(predicates), tuple(ordering))
