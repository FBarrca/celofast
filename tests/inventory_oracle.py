"""A plain-Python reference for object predicates, independent of PQL planning.

``matches`` defines the intended semantics: eq/ne treat None as a value,
ordering with a null operand is false, ``~`` is an exact complement, and a
relation holds when a related object (joined on the link's field) matches.
``MemoryClient`` serves generated types from in-memory objects using it.
"""

from __future__ import annotations

import operator
import re
import statistics
from collections.abc import Iterable, Mapping, Sequence

from celofast.sdk import Object, ObjectCollection
from celofast.sdk.definitions import (
    Aggregate,
    And,
    Comparison,
    Field,
    Not,
    Operand,
    Or,
    Predicate,
    Related,
    Sort,
)

_ORDERING = {"lt": operator.lt, "lte": operator.le, "gt": operator.gt, "gte": operator.ge}
Population = Mapping[str, Sequence[Object]]


def matches(predicate: Predicate, obj: Object, population: Population) -> bool:
    if isinstance(predicate, And):
        return all(matches(p, obj, population) for p in predicate.parts)
    if isinstance(predicate, Or):
        return any(matches(p, obj, population) for p in predicate.parts)
    if isinstance(predicate, Not):
        return not matches(predicate.part, obj, population)
    if isinstance(predicate, Comparison):
        left = value(predicate.field, obj, population)
        right = predicate.operand
        if isinstance(right, Operand):
            right = value(right, obj, population)
        if predicate.op == "eq":
            return left == right
        if predicate.op == "ne":
            return left != right
        if left is None:
            return False
        if predicate.op == "in":
            return left in right
        if predicate.op == "between":
            low, high = right
            return low <= left <= high
        if predicate.op == "like":
            return _like(right).fullmatch(left) is not None
        if right is None:
            return False
        return _ORDERING[predicate.op](left, right)
    if isinstance(predicate, Related):
        return bool(_related(predicate, obj, population))
    raise TypeError(type(predicate))


def _related(node, obj, population) -> list:
    """Related objects on a relation (Related or Aggregate) that match its predicate."""
    keys = [(getattr(obj, left), right) for left, right in node.relation.on]
    if any(key is None for key, _ in keys):
        return []
    return [
        related for related in population[node.relation.target.fields.object_type]
        if all(getattr(related, right) == key for key, right in keys)
        and (node.predicate is None or matches(node.predicate, related, population))
    ]


def value(operand: Operand, obj: Object, population: Population):
    """A field's loaded value, or an aggregate computed like Celonis PU functions."""
    if isinstance(operand, Field):
        return getattr(obj, operand.name)
    assert isinstance(operand, Aggregate)
    related = _related(operand, obj, population)
    values = [getattr(r, operand.field.name) for r in related]
    values = [v for v in values if v is not None]  # PU functions ignore nulls.
    if operand.function == "count":
        return len(values)
    if operand.function == "count_distinct":
        return len(set(values))
    if not values:
        return None
    if operand.function == "sum":
        return sum(values)
    if operand.function == "avg":
        return statistics.fmean(values)
    if operand.function == "median":
        return statistics.median_high(values)  # PU_MEDIAN takes the upper middle.
    return min(values) if operand.function == "min" else max(values)


def _like(pattern: str) -> re.Pattern[str]:
    """SQL LIKE: % is any text, _ one character; everything else is literal."""
    return re.compile("".join(
        ".*" if char == "%" else "." if char == "_" else re.escape(char) for char in pattern
    ), re.DOTALL)


def _sort_key(obj: Object, order: Iterable[Sort], population: Population) -> tuple:
    key = []
    for sort in order:
        result = value(sort.field, obj, population)
        key.append((result is None, result) if sort.ascending else _Reverse((result is None, result)))
    parts = obj.key if isinstance(obj.key, tuple) else (obj.key,)
    return (*key, *parts)


class _Reverse:
    def __init__(self, value):
        self.value = value

    def __lt__(self, other):
        return other.value < self.value

    def __eq__(self, other):
        return self.value == other.value


def select(object_type, predicates, order, population: Population) -> list:
    items = [
        obj for obj in population[object_type.fields.object_type]
        if all(matches(p, obj, population) for p in predicates)
    ]
    return sorted(items, key=lambda obj: _sort_key(obj, order, population))


class MemoryClient:
    """Implements the client's session contract over in-memory objects."""

    def __init__(self, model, objects: Iterable[Object]):
        self.model = model
        self.population: dict[str, list[Object]] = {t.fields.object_type: [] for t in model}
        for obj in objects:
            self.population[type(obj).fields.object_type].append(obj._attach(self))
        self.reads = 0

    def objects(self, object_type):
        return ObjectCollection(self, object_type)

    def _read(self, object_type, predicates, order, *, limit, offset):
        self.reads += 1
        items = select(object_type, predicates, order, self.population)
        return items[offset:offset + limit]
