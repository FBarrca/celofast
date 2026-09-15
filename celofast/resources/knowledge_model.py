"""Knowledge Model queries through the native PyCelonis connector."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

import pandas as pd
from pycelonis.ems.data_integration.data_model import DataModel
from pycelonis.ems.studio.content_node.knowledge_model import KnowledgeModel
import pycelonis.pql as pql
from pycelonis.pql.saola_connector import KnowledgeModelSaolaConnector

from celofast.exceptions import QueryValidationError
from celofast.query import query_to_pql
from celofast.resources.augmentation_table import AugmentationTableCollection
from celofast.types import ResourceMode
from celofast.sdk.capture import Capture, Source
from celofast.sdk.objects import KnowledgeModel as CapturedKnowledgeModel
from celofast.sdk.objects import Attribute, KPI, Record

if TYPE_CHECKING:
    from celofast.builder import Query


class KnowledgeModelHandle:
    """Execute reusable query definitions against one native Knowledge Model.

    All queries use KnowledgeModelSaolaConnector. Generated objects supply their
    PQL expressions; dependencies resolve against the connected Knowledge Model.

    Args:
        knowledge_model: Native PyCelonis Knowledge Model object.  In
            published mode this is a read-only final-layer reference created
            from the Apps package root key and KM key.
        data_model: Native Data Model resolved from the KM's final content.
        draft: Whether the connector should execute against the Studio draft;
            set to ``False`` for published Apps.  It defaults to ``True`` for
            backwards compatibility with direct construction.
        augmentation_tables: Optional shared augmentation-table collection.
            ``CeloFast`` supplies one cached by Data Model ID so KMs resolving
            to the same Data Model share table handles.
        source: Verified KM identity, if available from native content.
        capture_loader: Lazy provenance retrieval used when typed expressions
            require verification and native content omitted the source.

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
        augmentation_tables: AugmentationTableCollection | None = None,
        source: Source | None = None,
        capture_loader: Callable[[], Capture] | None = None,
    ) -> None:
        self._native = knowledge_model
        self._data_model = data_model
        self._draft = draft
        self._augmentation_tables = augmentation_tables
        self._source = source
        self._capture_loader = capture_loader
        self._connector = KnowledgeModelSaolaConnector(
            data_model,
            knowledge_model,
            draft=draft,
        )

    def bind(self, model: CapturedKnowledgeModel) -> KnowledgeModelHandle:
        """Validate the generated model source and return this native handle."""
        self._validate_capture(model.capture)
        return self

    def _validate_capture(self, capture: Capture) -> None:
        if self._source is None and self._capture_loader is not None:
            current = self._capture_loader()
            if current.definition.get("dataModelId") != self._data_model.id:
                raise QueryValidationError("Connected KM targets a different Data Model.")
            self._source = current.source
        if self._source is None or capture.source != self._source:
            raise QueryValidationError(
                "Generated model belongs to a different KM source or the source is unverified."
            )
        if capture.definition.get("dataModelId") != self._data_model.id:
            raise QueryValidationError("Generated model targets a different Data Model.")

    def select(
        self,
        columns: Record | Mapping[str, str | Attribute[Any] | KPI[Any]] | None = None,
        /,
        **named_columns: str | Attribute[Any] | KPI[Any],
    ) -> Query:
        """Select a whole record or output names supplied as a mapping or keywords."""
        from celofast.builder import Query

        return Query._select(self, columns, **named_columns)

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

    @property
    def augmentation_tables(self) -> AugmentationTableCollection:
        """Return Data Model-backed augmentation-table output operations.

        Returns:
            A cached :class:`AugmentationTableCollection` for the Data Model
            resolved from this Knowledge Model.

        Warning:
            Augmentation tables are not KM resources. Draft/published mode is
            used to resolve this handle's Knowledge Model, but mutations made
            through this collection write to the shared underlying Data Model
            and can affect every KM or View that consumes it.
        """

        if self._augmentation_tables is None:
            self._augmentation_tables = AugmentationTableCollection(self._data_model)
        return self._augmentation_tables

    def build(
        self,
        query: Mapping[str, object],
        *,
        variables: Mapping[str, str] | None = None,
    ) -> pql.PQL:
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

        return query_to_pql(
            query, variables=variables, validate_capture=self._validate_capture
        )

    def execute(
        self,
        query: Mapping[str, object],
        *,
        variables: Mapping[str, str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct: bool = False,
    ) -> pd.DataFrame:
        """Execute a query against the connected Knowledge Model.

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
        native_query = self.build(query, variables=variables)
        frame = pql.DataFrame.from_pql(native_query, saola_connector=self._connector)
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
