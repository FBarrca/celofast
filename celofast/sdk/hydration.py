"""Strict conversion of retrieved rows into immutable object instances.

The transport supplies plain Python values (``None`` for nulls). Hydration
decodes every field against its declared type, requires a non-null key, and
rejects conflicting values for the same identity. It never fills gaps.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any, Literal, TypeVar

from celofast.exceptions import ObjectIdentityError, ObjectValueError

if TYPE_CHECKING:
    from celofast.sdk.definitions import Field, Operand
    from celofast.sdk.objects import Object, _Session

ValueType = Literal["str", "int", "float", "bool", "date", "datetime"]
VALUE_TYPES: tuple[ValueType, ...] = ("str", "int", "float", "bool", "date", "datetime")
KEY_TYPES: tuple[ValueType, ...] = ("str", "int", "date", "datetime")

O = TypeVar("O", bound="Object")


def _accepts(value_type: ValueType, value: object) -> bool:
    if value_type == "str":
        return isinstance(value, str)
    if value_type == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == "float":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
    if value_type == "bool":
        return isinstance(value, bool)
    if value_type == "date":
        return isinstance(value, date) and not isinstance(value, datetime)
    return isinstance(value, datetime)


def check_filter_value(field: Operand[Any], value: object) -> None:
    """Reject filter values a field can never hold."""
    if value is None:
        if not field.nullable:
            raise ObjectValueError(f"{field.owner}.{field.name} is never null.")
        return
    if not _accepts(field.value_type, value):
        raise ObjectValueError(
            f"{field.owner}.{field.name} expects {field.value_type}, "
            f"not {type(value).__name__}."
        )
    if isinstance(value, datetime) and value.microsecond % 1000:
        raise ObjectValueError("Datetime filters require millisecond precision.")


def decode(field: Field[Any], raw: object) -> object:
    """Convert one transport value to the field's declared Python type."""
    if raw is None:
        if not field.nullable:
            raise ObjectIdentityError(f"{field.owner}.{field.name} key value is null.")
        return None
    value_type = field.value_type
    value: object = raw
    if value_type == "int" and isinstance(raw, float) and raw.is_integer():
        value = int(raw)  # Integer columns containing nulls arrive as floats.
    elif value_type == "float" and isinstance(raw, int) and not isinstance(raw, bool):
        value = float(raw)
    elif value_type == "bool" and type(raw) is int and raw in (0, 1):
        value = bool(raw)  # PQL has no boolean literal; flags are 0/1.
    elif value_type == "date" and isinstance(raw, datetime):
        if raw.timetz().replace(tzinfo=None) != time():
            raise ObjectValueError(
                f"{field.owner}.{field.name} is a date but received time {raw.time()}."
            )
        value = raw.date()
    if not _accepts(value_type, value):
        raise ObjectValueError(
            f"{field.owner}.{field.name} expects {value_type}, "
            f"received {type(raw).__name__} {raw!r}."
        )
    return value


def hydrate(
    object_type: type[O],
    rows: Iterable[Sequence[object]],
    *,
    context: _Session,
) -> list[O]:
    """Build one immutable instance per key, in first-seen row order."""
    definition = object_type.fields
    fields = list(definition)
    loaded: dict[object, dict[str, object]] = {}
    for row in rows:
        if len(row) != len(fields):
            raise ObjectValueError(
                f"{definition.object_type}: expected {len(fields)} values, received {len(row)}."
            )
        values = {field.name: decode(field, raw) for field, raw in zip(fields, row)}
        parts = tuple(values[name] for name in definition._key)
        key = parts[0] if len(parts) == 1 else parts
        previous = loaded.setdefault(key, values)
        if previous != values:
            changed = sorted(name for name in values if previous[name] != values[name])
            raise ObjectIdentityError(
                f"{definition.object_type} key {key!r} has conflicting values for "
                f"{', '.join(changed)}; each property must resolve to one value per key."
            )
    return [
        object_type(key=key, **values)._attach(context)  # type: ignore[call-arg]
        for key, values in loaded.items()
    ]
