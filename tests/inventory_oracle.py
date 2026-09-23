"""A plain-Python reference for object predicates, independent of PQL planning.

``matches`` defines the intended semantics: eq/ne treat None as a value,
ordering with a null operand is false, ``~`` is an exact complement, and a
relation holds when a related object (joined on the link's field) matches.
``MemoryClient`` serves generated types from in-memory objects using it.
"""

from __future__ import annotations

import operator
import re
from collections.abc import Iterable, Mapping, Sequence

from celofast.sdk import Object, ObjectCollection
from celofast.sdk.definitions import And, Comparison, Field, Not, Or, Predicate, Related, Sort

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
        left = getattr(obj, predicate.field.name)
        right = predicate.operand
        if isinstance(right, Field):
            right = getattr(obj, right.name)
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
        values = [(getattr(obj, left), right) for left, right in predicate.link.on]
        if any(value is None for value, _ in values):
            return False
        return any(
            all(getattr(related, right) == value for value, right in values)
            and (predicate.predicate is None or matches(predicate.predicate, related, population))
            for related in population[predicate.target.object_type]
        )
    raise TypeError(type(predicate))


def _like(pattern: str) -> re.Pattern[str]:
    """SQL LIKE: % is any text, _ one character; everything else is literal."""
    return re.compile("".join(
        ".*" if char == "%" else "." if char == "_" else re.escape(char) for char in pattern
    ), re.DOTALL)


def _sort_key(obj: Object, order: Iterable[Sort]) -> tuple:
    key = []
    for sort in order:
        value = getattr(obj, sort.field.name)
        key.append((value is None, value) if sort.ascending else _Reverse((value is None, value)))
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
    return sorted(items, key=lambda obj: _sort_key(obj, order))


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
