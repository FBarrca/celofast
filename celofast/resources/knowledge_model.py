"""Knowledge Model query execution through PyCelonis's native connector."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
from pycelonis.ems.data_integration.data_model import DataModel
from pycelonis.ems.studio.content_node.knowledge_model import KnowledgeModel
from pycelonis.pql import DataFrame
from pycelonis.pql.saola_connector import KnowledgeModelSaolaConnector
from saolapy.pql.base import PQL

from celofast.exceptions import QueryValidationError
from celofast.query import query_to_pql
from celofast.types import ResourceMode


class KnowledgeModelHandle:
    """Execute reusable query definitions against one native Knowledge Model.

    The handle is intentionally thin: KPI, record-attribute, filter, and
    Knowledge Model variable semantics remain owned by PyCelonis.  CeloFast
    only converts the dictionary contract to SaolaPy ``PQL`` and chooses the
    native ``KnowledgeModelSaolaConnector`` with the resolved Data Model.

    Args:
        knowledge_model: Native PyCelonis Knowledge Model object.  In
            published mode this is a read-only final-layer reference created
            from the Apps package root key and KM key.
        data_model: Native Data Model resolved from the KM's final content.
        draft: Whether the connector should execute against the Studio draft;
            set to ``False`` for published Apps.  It defaults to ``True`` for
            backwards compatibility with direct construction.

    Notes:
        The ``native`` and ``data_model`` properties provide escape hatches to
        PyCelonis APIs not represented by this convenience wrapper.
    """

    def __init__(
        self,
        knowledge_model: KnowledgeModel,
        data_model: DataModel,
        *,
        draft: bool = True,
    ) -> None:
        self._native = knowledge_model
        self._data_model = data_model
        self._draft = draft
        self._connector = KnowledgeModelSaolaConnector(
            data_model,
            knowledge_model,
            draft=draft,
        )

    @property
    def mode(self) -> ResourceMode:
        """Return the lifecycle context used for KM exports."""

        return "draft" if self._draft else "published"

    @property
    def native(self) -> KnowledgeModel:
        """Return the underlying native PyCelonis Knowledge Model.

        Returns:
            The exact native object used by the connector.  For published
            Apps this is a read-only final-layer reference; mutation-oriented
            Studio KM methods are not supported through it.
        """

        return self._native

    @property
    def data_model(self) -> DataModel:
        """Return the Data Model used by the native KM connector.

        Returns:
            The resolved :class:`pycelonis.ems.data_integration.data_model.DataModel`.
            It is selected from the KM's final server-side content rather than
            by parsing package variables in raw YAML.
        """

        return self._data_model

    def build(
        self,
        query: Mapping[str, object],
        *,
        variables: Mapping[str, str] | None = None,
    ) -> PQL:
        """Compile a reusable query definition without executing it.

        Args:
            query: Mapping with non-empty ``columns`` and optional native PQL
                ``filters`` and ``order_by`` entries.
            variables: Optional exact string bindings for ``${name}``
                placeholders.  Bindings apply to query expressions only;
                server-managed KM variables are still resolved by Celonis.

        Returns:
            A native SaolaPy :class:`~saolapy.pql.base.PQL` object suitable for
            inspection, serialization, or execution through PyCelonis.

        Raises:
            QueryValidationError: If the query or variable mapping is invalid.
            UnresolvedVariableError: If an executable expression contains an
                unbound placeholder.

        Example:
            >>> pql = km.build({"columns": {"Supplier": '"Vendor"."Name"'}})
            >>> pql.columns[0].name
            'Supplier'
        """

        return query_to_pql(query, variables=variables)

    def execute(
        self,
        query: Mapping[str, object],
        *,
        variables: Mapping[str, str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct: bool = False,
    ) -> pd.DataFrame:
        """Execute a query through PyCelonis's native KM connector.

        Args:
            query: Reusable dictionary query definition.
            variables: Optional exact string bindings for query placeholders.
            limit: Maximum number of rows, or ``None`` to request all rows.
                The value is passed to SaolaPy ``to_pandas`` rather than
                embedded in PQL.
            offset: Number of rows to skip before returning results, or
                ``None`` for the connector default.  It is passed to
                ``to_pandas`` alongside ``limit``.
            distinct: Whether SaolaPy should request distinct rows.

        Returns:
            A pandas ``DataFrame`` returned by ``DataFrame.to_pandas``.

        Raises:
            QueryValidationError: If the query, variables, limit, offset, or
                distinct flag is invalid.
            Exception: PyCelonis/SaolaPy execution errors are deliberately
                propagated unchanged, including their original exception
                chains.
        """

        self._validate_execution_options(limit, offset, distinct)
        pql = self.build(query, variables=variables)
        frame = DataFrame.from_pql(pql, saola_connector=self._connector)
        return frame.to_pandas(limit=limit, offset=offset, distinct=distinct)

    @staticmethod
    def _validate_execution_options(
        limit: int | None,
        offset: int | None,
        distinct: bool,
    ) -> None:
        for name, value in (("limit", limit), ("offset", offset)):
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise QueryValidationError(
                    f"{name} must be a non-negative integer or None."
                )
        if not isinstance(distinct, bool):
            raise QueryValidationError("distinct must be a boolean.")
