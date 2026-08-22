"""Typed Studio and published View table handles backed by PyCelonis."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from types import MappingProxyType

import pandas as pd
from pycelonis.ems.apps.content_node.view.component import Table
from pycelonis.ems.apps.content_node.view.content import ViewContent
from pycelonis.ems.apps.content_node.view import PublishedView
from pycelonis.ems.studio.content_node.view import View

from celofast.exceptions import (
    AmbiguousTableError,
    QueryValidationError,
    TableNotFoundError,
)
from celofast.query import (
    QueryDefinition,
    query_from_pql,
    validate_query,
    validate_variables,
)
from celofast.resources.knowledge_model import KnowledgeModelHandle

NativeView = View | PublishedView


class ViewHandle:
    """Expose typed table components from one Studio or published View.

    A handle is built from PyCelonis's validated :class:`ViewContent`, so it
    discovers native ``Table`` components in both root components and tab
    components.  It does not recreate View semantics: table columns, filters,
    KPI references, and sort expressions come directly from
    ``Table.get_query()``.

    Args:
        view: Native Studio draft or published Apps View.
        content: Typed content parsed by PyCelonis ``ViewContent``.
        knowledge_model: Lazy factory for the KM named by the View metadata.
        variables: Optional View-level exact string bindings.  Published View
            input defaults are loaded first and these values take precedence.

    Notes:
        The associated KM/Data Model is resolved lazily.  Use ``native`` or
        ``content`` when a caller needs the underlying PyCelonis objects.
    """

    def __init__(
        self,
        view: NativeView,
        content: ViewContent,
        knowledge_model: Callable[[], KnowledgeModelHandle],
        *,
        variables: Mapping[str, str] | None = None,
    ) -> None:
        self._native = view
        self._content = content
        self._km_factory = knowledge_model
        self._km: KnowledgeModelHandle | None = None

        defaults: dict[str, str] = {}
        for definition in view.input_variable_definitions or []:
            if (
                definition is not None
                and definition.key
                and definition.default_value is not None
            ):
                defaults[definition.key] = definition.default_value
        defaults.update(validate_variables(variables))
        self._variables = MappingProxyType(defaults)

        tables: list[ViewTableHandle] = []
        tables.extend(self._table_handles(content.components, tab_name=None))
        for tab in content.tabs:
            tables.extend(self._table_handles(tab.components, tab_name=tab.name))
        self._tables = tuple(tables)

    @property
    def native(self) -> NativeView:
        """Return the underlying native Studio or Apps View.

        Returns:
            The exact native View supplied by the package resolver.
        """

        return self._native

    @property
    def content(self) -> ViewContent:
        """Return PyCelonis's validated, typed View content.

        Returns:
            The :class:`pycelonis.ems.apps.content_node.view.content.ViewContent`
            parsed from the View's serialized draft definition or fetched from
            the published Apps View.
        """

        return self._content

    @property
    def km(self) -> KnowledgeModelHandle:
        """Return the lazily resolved Knowledge Model associated with the View.

        Returns:
            A cached :class:`KnowledgeModelHandle` selected using
            ``content.metadata.knowledge_model_key``.

        Raises:
            ResourceNotFoundError: If the metadata key is not in the Package.
            ResourceResolutionError: If its final Data Model is inaccessible.
        """

        if self._km is None:
            self._km = self._km_factory()
        return self._km

    @property
    def variables(self) -> Mapping[str, str]:
        """Return immutable View-level template bindings.

        Returns:
            A read-only mapping containing published View input defaults,
            overridden by bindings passed to :meth:`CeloFast.view`.  The
            mapping is used as the base for table execution; per-call
            ``variables`` supplied to :meth:`ViewTableHandle.execute` take
            final precedence.
        """

        return self._variables

    @property
    def tables(self) -> tuple["ViewTableHandle", ...]:
        """Return all typed table components in stable content order.

        Returns:
            A tuple containing tables in root components first, followed by
            each tab's components.  Each handle exposes its native component,
            component ID, display name, and tab name.
        """

        return self._tables

    def table(self, name_or_id: str) -> "ViewTableHandle":
        """Find one table by exact component ID or exact display name.

        Lookup checks IDs first, then display names.  An ID is always
        unambiguous; duplicate display names are rejected so callers do not
        accidentally execute the wrong table.

        Args:
            name_or_id: Exact native component ID or exact configured display
                name.

        Returns:
            The matching :class:`ViewTableHandle`.

        Raises:
            TableNotFoundError: If no table has that ID or name.
            AmbiguousTableError: If multiple tables share the display name.
                The exception lists matching IDs and tabs; use an ID to select
                one explicitly.
        """

        id_matches = [table for table in self._tables if table.id == name_or_id]
        if id_matches:
            return id_matches[0]

        name_matches = [table for table in self._tables if table.name == name_or_id]
        if not name_matches:
            raise TableNotFoundError(
                f"Table {name_or_id!r} was not found in View {self._native.key!r}."
            )
        if len(name_matches) > 1:
            locations = ", ".join(
                f"{table.id!r} (tab {table.tab_name!r})" for table in name_matches
            )
            raise AmbiguousTableError(
                f"Table name {name_or_id!r} is ambiguous; use a component ID: "
                f"{locations}."
            )
        return name_matches[0]

    def _table_handles(
        self,
        components: Iterable[object],
        *,
        tab_name: str | None,
    ) -> list["ViewTableHandle"]:
        return [
            ViewTableHandle(self, component, tab_name=tab_name)
            for component in components
            if isinstance(component, Table)
        ]


class ViewTableHandle:
    """Export and execute one native PyCelonis View table component.

    Table queries are obtained from ``component.get_query()``.  This preserves
    every native column (including configured data-source attributes hidden in
    the UI), native ``FILTER @...;`` references, and configured sorting.

    The handle is normally obtained from :meth:`ViewHandle.table` rather than
    constructed directly.  Its ``component`` property remains available as a
    native PyCelonis escape hatch.
    """

    def __init__(
        self,
        view: ViewHandle,
        component: Table,
        *,
        tab_name: str | None,
    ) -> None:
        self._view = view
        self._component = component
        self._tab_name = tab_name

    @property
    def id(self) -> str:
        """Return the stable native component ID used for unambiguous lookup.

        Returns:
            The table component's PyCelonis ID.
        """
        return self._component.id

    @property
    def name(self) -> str:
        """Return the configured display name, falling back to ``id``.

        Returns:
            The table's exact display name when configured; otherwise its
            component ID.
        """
        name = getattr(self._component.settings, "name", None)
        return name if isinstance(name, str) and name else self.id

    @property
    def tab_name(self) -> str | None:
        """Return the containing tab name, or ``None`` for root components.

        Returns:
            The exact native tab display name when the table is nested in a
            View tab; ``None`` when it belongs to the View root.
        """
        return self._tab_name

    @property
    def component(self) -> Table:
        """Return the underlying typed PyCelonis ``Table`` component.

        Returns:
            The native component used to obtain the table query and filters.
            Callers can use this property for PyCelonis features not exposed
            by CeloFast.
        """

        return self._component

    def to_query(
        self,
        *,
        inherit_filters_from: Sequence[str] = (),
        extra_filters: Iterable[str] = (),
    ) -> QueryDefinition:
        """Export this table's native query as a symbolic dictionary.

        Args:
            inherit_filters_from: Ordered table selectors (IDs or unique
                names).  Each selected table's configured filters are
                appended in request order after this table's own filters.
            extra_filters: Iterable of complete native PQL filter statements.
                These are appended after all inherited filters.

        Returns:
            A fresh :class:`~celofast.QueryDefinition` containing every column,
            native filter, and ``order_by`` expression returned by
            ``Table.get_query()``.  KPI and Knowledge Model references remain
            symbolic for server-side resolution; no KM execution occurs.

        Raises:
            QueryValidationError: If selector/filter arguments are strings in
                place of iterables, contain invalid values, or the native
                query has duplicate/invalid fields.
            TableNotFoundError: If an inherited table selector is unknown.
            AmbiguousTableError: If an inherited display name is duplicated.
        """

        if isinstance(inherit_filters_from, str):
            raise QueryValidationError(
                "inherit_filters_from must be a sequence of table names or IDs."
            )
        if isinstance(extra_filters, str):
            raise QueryValidationError(
                "extra_filters must be an iterable of complete PQL filter strings."
            )

        definition = query_from_pql(self._component.get_query())
        filters = list(definition["filters"])
        for selector in inherit_filters_from:
            inherited = self._view.table(selector).component.get_filters()
            filters.extend(filter_.query for filter_ in inherited)
        filters.extend(extra_filters)
        definition["filters"] = filters
        return validate_query(definition)

    def execute(
        self,
        *,
        inherit_filters_from: Sequence[str] = (),
        extra_filters: Iterable[str] = (),
        variables: Mapping[str, str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct: bool = False,
    ) -> pd.DataFrame:
        """Export and execute this table through its associated Knowledge Model.

        Args:
            inherit_filters_from: Ordered table selectors whose configured
                filters should be inherited before ``extra_filters``.
            extra_filters: Complete native PQL filter statements appended last.
            variables: Per-call exact string bindings for ``${name}``
                placeholders.  Precedence is execution values, then the
                View-level values, then published View input defaults.
            limit: Maximum number of rows, or ``None`` for no implicit limit.
            offset: Number of rows to skip, or ``None`` for the connector
                default.  Pagination is passed to SaolaPy ``to_pandas``.
            distinct: Whether to request distinct rows from SaolaPy.

        Returns:
            The pandas ``DataFrame`` returned by the native KM connector.

        Raises:
            QueryValidationError: If filters, variables, or execution options
                are malformed.
            TableNotFoundError: If an inherited table selector is unknown.
            AmbiguousTableError: If an inherited display name is ambiguous.
            Exception: Native PyCelonis/SaolaPy execution errors are preserved
                unchanged.
        """

        merged_variables = dict(self._view.variables)
        merged_variables.update(validate_variables(variables))
        return self._view.km.execute(
            self.to_query(
                inherit_filters_from=inherit_filters_from,
                extra_filters=extra_filters,
            ),
            variables=merged_variables,
            limit=limit,
            offset=offset,
            distinct=distinct,
        )
