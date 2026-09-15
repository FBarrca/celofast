"""Immutable KM queries layered over the existing dictionary execution API."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import pandas as pd
import pycelonis.pql as pql

from celofast.exceptions import QueryValidationError
from celofast.expressions import Predicate
from celofast.query import QueryDefinition, validate_query
from celofast.sdk.objects import Attribute, Filter, KPI, KnowledgeModel, Record, Sort

if TYPE_CHECKING:
    from celofast.resources.knowledge_model import KnowledgeModelHandle

Column = str | Attribute[Any] | KPI[Any]


@dataclass(frozen=True)
class Query:
    """A reusable query bound to one KM; only execute() requests data.

    Create through ``km.select(...)``. Every composition method returns a new
    query. Captured objects are retained until compilation so their source
    information survives reuse and dictionary export.
    """

    _handle: KnowledgeModelHandle
    _columns: tuple[tuple[str, Column], ...]
    _filters: tuple[str | Filter | Predicate, ...] = ()
    _ordering: tuple[tuple[Column, bool], ...] = ()

    def __post_init__(self) -> None:
        validate_query(self.to_query())

    @classmethod
    def _select(
        cls,
        handle: KnowledgeModelHandle,
        columns: Record | Mapping[str, Column] | None = None,
        /,
        **named_columns: Column,
    ) -> Query:
        selected: dict[str, Column] = {}
        if isinstance(columns, Record):
            handle.bind(KnowledgeModel(columns.capture))
            try:
                for attribute in columns._query_attributes():
                    alias = attribute.id
                    if alias in selected:
                        raise QueryValidationError(f"Duplicate record attribute ID: {alias!r}.")
                    if isinstance(alias, str):
                        selected[alias] = attribute
            except (KeyError, IndexError, AttributeError, TypeError) as exc:
                raise QueryValidationError("Unknown or invalid captured record.") from exc
            if not selected:
                raise QueryValidationError("Selected record has no queryable attributes.")
        elif isinstance(columns, Mapping):
            selected.update(columns)
        elif columns is not None:
            raise QueryValidationError("select() requires a record or column mapping.")
        duplicates = selected.keys() & named_columns.keys()
        if duplicates:
            raise QueryValidationError(
                f"Duplicate output column(s): {', '.join(sorted(duplicates))}."
            )
        selected.update(named_columns)
        return cls(handle, tuple(selected.items()))

    def where(self, *filters: str | Filter | Predicate) -> Query:
        """Append native or captured filters, combined with AND by Celonis."""
        return replace(self, _filters=(*self._filters, *filters))

    def order_by(self, *expressions: Column | Sort) -> Query:
        """Replace ordering; plain expressions sort ascending. No args clears it."""
        ordering: list[tuple[Column, bool]] = []
        for expression in expressions:
            if isinstance(expression, Sort):
                if not isinstance(expression.expression, (Attribute, KPI)):
                    raise QueryValidationError("Only attributes and KPIs can be sorted.")
                ordering.append((expression.expression, expression.ascending))
            else:
                ordering.append((expression, True))
        return replace(self, _ordering=tuple(ordering))

    def to_query(self) -> QueryDefinition:
        """Return an independent dictionary, retaining captured objects."""
        return {
            "columns": dict(self._columns),
            "filters": list(self._filters),
            "order_by": [
                {"pql": expression, "ascending": ascending}
                for expression, ascending in self._ordering
            ],
        }

    def build(self, *, variables: Mapping[str, str] | None = None) -> pql.PQL:
        """Compile native PQL without executing the query."""
        return self._handle.build(self.to_query(), variables=variables)

    def execute(
        self,
        *,
        variables: Mapping[str, str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct: bool = False,
    ) -> pd.DataFrame:
        """Fetch live data using the existing native KM execution path."""
        return self._handle.execute(
            self.to_query(), variables=variables, limit=limit,
            offset=offset, distinct=distinct,
        )
