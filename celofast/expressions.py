"""Offline, immutable attribute predicates with PQL literal encoding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import math
from typing import Any

from celofast.exceptions import QueryValidationError
from celofast.sdk.objects import Attribute


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
    raise QueryValidationError(
        "Attribute comparisons require a string, finite number, boolean, date, or None."
    )


@dataclass(frozen=True)
class Predicate:
    """An attribute equality filter retaining its captured source and defaults."""

    attribute: Attribute[Any]
    _literal: str | None

    @classmethod
    def equal(cls, attribute: Attribute[Any], value: object) -> Predicate:
        if not isinstance(attribute.pql, str) or not attribute.pql.strip():
            raise QueryValidationError("Attribute has no queryable PQL expression.")
        return cls(attribute, None if value is None else _literal(value))

    def render(self, expression: str) -> str:
        suffix = "IS NULL" if self._literal is None else f"= {self._literal}"
        # A newline keeps a trailing line comment in the attribute from eating
        # the comparison. Bind the attribute before adding the literal value.
        return f"FILTER ({expression}\n) {suffix};"

    @property
    def pql(self) -> str:
        expression = self.attribute.pql
        if not isinstance(expression, str) or not expression.strip():
            raise QueryValidationError("Attribute has no queryable PQL expression.")
        return self.render(expression)

    def __bool__(self) -> bool:
        raise QueryValidationError("Pass predicates to where(); do not use Python and/or.")
