"""Private translation of object reads into a single KM export query.

A read loads every generated field, applies one filter built from the
predicate tree, and orders by the requested fields and then the key so pages
are deterministic. Applications never see the expressions produced here.

Every condition is rendered two-valued (``CASE WHEN ... THEN 1 ELSE 0 END``),
so ``~`` is an exact complement even when values are null.

Relationship predicates are rendered in the same query:

* to-one ``has()`` pulls the related type's expressions onto the filtered row
  with ``BIND``, so unmatched rows see NULL;
* to-many ``any()`` counts matching related rows with ``PU_COUNT`` on the
  filtered row's table, rendering the nested condition on the related table;
* aggregates (``count``, ``sum``, ``avg``, ...) render as the matching
  Pull-Up function and compare or sort like any column;
* activity conditions on an event log (``contains``, ...) render as
  ``MATCH_ACTIVITIES`` on the log's activity column, a flag per lead object;
* Object Link relations count, per object, the links of the Data Model's
  Object Link graph at one of its ends, with ``LINK_SOURCE`` and ``LINK_TARGET``.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import pycelonis.pql as pql

from celofast.exceptions import QueryValidationError
from celofast.sdk.definitions import (
    Aggregate,
    And,
    Comparison,
    Field,
    Linked,
    Not,
    ObjectDefinition,
    Operand,
    Or,
    Predicate,
    Process,
    Related,
    Sort,
)
from celofast.sdk.objects import ObjectLinkRelation

if TYPE_CHECKING:
    from celofast.sdk.objects import Object

_ORDERING = {"lt": "<", "lte": "<=", "gt": ">", "gte": ">="}
# MATCH_ACTIVITIES specifiers; ``excludes`` is the complement of NODE_ANY, so
# it also holds for an object without events.
_MATCH = {"contains": "NODE", "starts_with": "STARTING", "ends_with": "ENDING", "excludes": "NODE_ANY"}

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
    raise QueryValidationError(f"Unsupported filter value {type(value).__name__}.")


def _table(definition: ObjectDefinition) -> str:
    # Only types that read a plain Data Model table have relations.
    return f'"{definition._table}"'


def _links(
    definition: ObjectDefinition, bind: Callable[[str], str], *, source: bool, other: object = None,
) -> str:
    """Per object: its Object Links as the ``source`` (else target) end.

    With ``other``, only the links whose opposite end is the object keyed
    ``other``. The links live in an internal edge table; ``PU_FIRST`` and
    ``BIND`` bring the count back to the object's table, as the Celonis KM
    attributes on Object Link do.
    """
    table, key = _table(definition), bind(definition.key_fields[0].expression).strip()
    ends = (f"LINK_SOURCE({key})", f"LINK_TARGET({key})")
    own, opposite = ends if source else ends[::-1]
    condition = "" if other is None else f", {opposite} = {_literal(other)}"
    return (
        f"COALESCE(PU_FIRST({table}, CASE WHEN {own} = {key} THEN BIND(COMMON_TABLE({own}, {key}), "
        f"PU_COUNT(DOMAIN_TABLE({own}), {own}{condition})) END), 0)"
    )


def _case(test: str) -> str:
    return f"CASE WHEN {test} THEN 1 ELSE 0 END"


class _Renderer:
    def __init__(self, bind: Callable[[str], str]) -> None:
        self.bind = bind

    def expression(self, operand: Operand[Any], pull: Pull = _identity) -> str:
        if isinstance(operand, Aggregate) and isinstance(operand.relation, ObjectLinkRelation):
            relation = operand.relation
            return pull(_links(relation.source.fields, self.bind, source=relation.ends == "targets"))
        if isinstance(operand, Aggregate):
            # A Pull-Up function on the source table; its condition is
            # evaluated on the related table itself.
            condition = "" if operand.predicate is None else f", {self.condition(operand.predicate)}"
            source = _table(operand.relation.source.fields)
            return pull(f"PU_{operand.function.upper()}({source}, {self.expression(operand.field)}{condition})")
        assert isinstance(operand, Field)
        # A newline keeps a trailing line comment from consuming what follows.
        return pull(f"({self.bind(operand.expression)}\n)")

    def condition(self, predicate: Predicate, pull: Pull = _identity, negate: bool = False) -> str:
        if isinstance(predicate, (And, Or)):
            # De Morgan keeps negation on two-valued atoms.
            joiner = " AND " if isinstance(predicate, And) != negate else " OR "
            return "(" + joiner.join(self.condition(p, pull, negate) for p in predicate.parts) + ")"
        if isinstance(predicate, Not):
            return self.condition(predicate.part, pull, not negate)
        if isinstance(predicate, Comparison):
            indicator, negated = self.comparison(predicate, pull)
        elif isinstance(predicate, Related):
            indicator, negated = self.related(predicate, pull), False
        elif isinstance(predicate, Linked):
            # The targets of an object are the target end of its links, and vice versa.
            relation = predicate.relation
            count = _links(relation.target.fields, self.bind, source=relation.ends == "sources", other=predicate.key)
            indicator, negated = _case(f"{pull(count)} > 0"), False
        elif isinstance(predicate, Process):
            indicator, negated = self.process(predicate, pull), predicate.mode == "excludes"
        else:
            raise QueryValidationError(f"Unsupported predicate {type(predicate).__name__}.")
        return f"{indicator} = {0 if negate != negated else 1}"

    def comparison(self, predicate: Comparison, pull: Pull) -> tuple[str, bool]:
        """A 0/1 expression, and whether the predicate is its complement."""
        left = self.expression(predicate.field, pull)
        op, operand = predicate.op, predicate.operand
        if op == "in":
            assert isinstance(operand, tuple)
            return _case(f"{left} IN ({', '.join(_literal(v) for v in operand)})"), False
        if op == "between":
            assert isinstance(operand, tuple)
            low, high = operand
            return _case(f"{left} BETWEEN {_literal(low)} AND {_literal(high)}"), False
        if op == "like":
            return _case(f"{left} LIKE {_literal(operand)}"), False
        if operand is None:
            return _case(f"{left} IS NULL"), op == "ne"
        if isinstance(operand, Operand):
            right = self.expression(operand, pull)
            if op in ("eq", "ne"):
                both_null = f"{left} IS NULL AND {right} IS NULL"
                return f"CASE WHEN {left} = {right} THEN 1 WHEN {both_null} THEN 1 ELSE 0 END", op == "ne"
            return _case(f"{left} {_ORDERING[op]} {right}"), False
        if op in ("eq", "ne"):
            return _case(f"{left} = {_literal(operand)}"), op == "ne"
        return _case(f"{left} {_ORDERING[op]} {_literal(operand)}"), False

    def process(self, process: Process, pull: Pull) -> str:
        if pull is not _identity:
            raise QueryValidationError(
                f"{process.relation.name}.{process.mode}() is a condition on "
                f"{process.owner._object_type} itself; it cannot be used inside has()."
            )
        activity = self.bind(process.relation.target.fields.activity.expression).strip()
        names = ", ".join(_literal(name) for name in process.activities)
        return _case(f"MATCH_ACTIVITIES({activity}, {_MATCH[process.mode]}[{names}]) = 1")

    def related(self, related: Related, pull: Pull) -> str:
        relation = related.relation
        if isinstance(relation, ObjectLinkRelation):
            count = _links(relation.source.fields, self.bind, source=relation.ends == "targets")
            return _case(f"{pull(count)} > 0")
        source, target = relation.source.fields, relation.target.fields
        key = target.key_fields[0]
        if relation.cardinality == "one":
            table = _table(source)
            to_target: Pull = lambda e: pull(f"BIND({table}, {e})")  # noqa: E731
            exists = f"{self.expression(key, to_target)} IS NOT NULL"
            if related.predicate is None:
                return _case(exists)
            return _case(f"{exists} AND {self.condition(related.predicate, to_target)}")
        # To-many: count related rows on the source table. The nested
        # condition is evaluated on the related table itself.
        condition = "" if related.predicate is None else f", {self.condition(related.predicate)}"
        count = pull(f"PU_COUNT({_table(source)}, {self.expression(key)}{condition})")
        return _case(f"{count} > 0")


def plan_read(
    object_type: type[Object],
    predicates: tuple[Predicate, ...],
    order: tuple[Sort, ...] = (),
    *,
    bind: Callable[[str], str],
) -> pql.PQL:
    """Query every field of ``object_type`` as columns ``f0``, ``f1``, ...

    Rows are ordered by ``order``, then by the type's default order: the key,
    or for events the timestamp and then the key.

    ``bind`` replaces the ``${name}`` input placeholders of each field
    expression. With DISTINCT, Celonis ignores
    ORDER BY expressions that are not selected (verified live), so sort-only
    expressions such as aggregates are selected too, as columns ``s0``, ...
    after the fields.
    """
    renderer = _Renderer(bind)
    definition = object_type.fields
    columns = [(f"f{i}", renderer.expression(field)) for i, field in enumerate(definition)]
    ordering = [(renderer.expression(sort.field), sort.ascending) for sort in order]
    ordering += [(renderer.expression(field), True) for field in definition._default_order]
    selected = {expression for _, expression in columns}
    for expression, _ in ordering:
        if expression not in selected:
            columns.append((f"s{len(columns) - len(definition)}", expression))
            selected.add(expression)
    return pql.PQL(
        columns=[pql.PQLColumn(name=name, query=query) for name, query in columns],
        filters=[pql.PQLFilter(query=f"FILTER {renderer.condition(p)};") for p in predicates],
        order_by_columns=[pql.OrderByColumn(query=q, ascending=a) for q, a in ordering],
    )
