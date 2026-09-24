"""Studio and published View tables and inputs, backed by PyCelonis.

``cf.view(key)`` returns a :class:`ViewHandle`; ``view[selector]`` returns a
table or input by component ID or unique display name. Tables run their
native ``Table.get_query()`` through the View's Knowledge Model, with every
``${name}`` input placeholder bound to the input's current value.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from functools import cached_property
from types import MappingProxyType
from typing import TYPE_CHECKING, TypedDict, TypeVar

import pandas as pd
import pycelonis.pql as pql
from pycelonis.ems.apps.content_node.view import PublishedView
from pycelonis.ems.apps.content_node.view.component import Component, Table
from pycelonis.ems.apps.content_node.view.content import ViewContent
from pycelonis.ems.studio.content_node.knowledge_model import KnowledgeModel
from pycelonis.ems.studio.content_node.view import View
from pycelonis.service.package_manager.service import AppMode, PackageManagerService
from typing_extensions import NotRequired

from celofast.exceptions import (
    AmbiguousComponentError,
    AmbiguousTableError,
    ComponentNotFoundError,
    QueryValidationError,
    TableNotFoundError,
)
from celofast.resources.view_input import (
    INPUT_HANDLES,
    InputVariableValue,
    ViewElement,
    ViewInputHandle,
)
from celofast.sdk.expressions import bind_inputs, placeholders

if TYPE_CHECKING:
    from celofast.resources.knowledge_model import KnowledgeModelConnection

NativeView = View | PublishedView
E = TypeVar("E", bound=ViewElement)


class OrderByDefinition(TypedDict):
    """One ordering of a :class:`QueryDefinition`: a PQL expression and direction."""

    pql: str
    ascending: NotRequired[bool]


class QueryDefinition(TypedDict):
    """A View table's query as plain, serializable PQL strings.

    ``columns`` maps output names to expressions in table order; ``filters``
    are complete filter statements; ``order_by`` lists the sorting. KPI and
    KM filter references such as ``FILTER @active;`` stay symbolic.
    """

    columns: dict[str, str]
    filters: NotRequired[list[str]]
    order_by: NotRequired[list[OrderByDefinition]]


def _find(elements: Sequence[E], selector: str, missing: type[Exception],
          ambiguous: type[Exception], kind: str, view: str) -> E:
    """The element with that exact component ID, else that unique display name."""
    matches = [e for e in elements if e.id == selector] or [e for e in elements if e.name == selector]
    if not matches:
        raise missing(f"{kind} {selector!r} was not found in View {view!r}.")
    if len(matches) > 1:
        locations = ", ".join(f"{e.id!r} (tab {e.tab_name!r})" for e in matches)
        raise ambiguous(f"{kind} {selector!r} is ambiguous; use a component ID: {locations}.")
    return matches[0]


class ViewHandle:
    """The tables and inputs of one Studio or published View.

    Elements come from PyCelonis's validated :class:`ViewContent`, in root
    components first, then each tab. The View's Knowledge Model is resolved
    only when a table or data-backed dropdown runs a query.
    """

    def __init__(
        self,
        view: NativeView,
        content: ViewContent,
        knowledge_model: Callable[[], KnowledgeModelConnection],
        native_knowledge_model: Callable[[], KnowledgeModel] | None = None,
    ) -> None:
        self._native = view
        self._content = content
        self._km_factory = knowledge_model
        self._native_km_factory = native_knowledge_model or (lambda: self.km.native)
        elements: list[ViewElement] = []
        for tab_name, components in [(None, content.components)] + [
            (tab.name, tab.components) for tab in content.tabs
        ]:
            for component in components:
                if isinstance(component, Table):
                    elements.append(ViewTableHandle(self, component, tab_name=tab_name))
                elif isinstance(component, Component) and component.type_ in INPUT_HANDLES:
                    elements.append(INPUT_HANDLES[component.type_](self, component, tab_name=tab_name))
        self._elements = tuple(elements)

    @property
    def native(self) -> NativeView:
        """The native PyCelonis View."""
        return self._native

    @property
    def content(self) -> ViewContent:
        """The View's typed PyCelonis content."""
        return self._content

    @cached_property
    def km(self) -> KnowledgeModelConnection:
        """The View's Knowledge Model, resolved with its Data Model on first use."""
        return self._km_factory()

    @cached_property
    def native_km(self) -> KnowledgeModel:
        """The View's native Knowledge Model, without resolving its Data Model."""
        return self._native_km_factory()

    @property
    def elements(self) -> tuple[ViewElement, ...]:
        """Supported tables and inputs, root components first, then each tab."""
        return self._elements

    @cached_property
    def input_definitions(self) -> Mapping[str, object]:
        """KM and View-scoped input variable definitions by key.

        A View-scoped definition overrides a KM definition of the same key.
        """
        definitions: dict[str, object] = {}
        for source, sources in (
            ("Knowledge Model", self.native_km.input_variable_definitions),
            ("View", getattr(self._native, "input_variable_definitions", None)),
        ):
            keys = [d.key for d in sources or () if d is not None and d.key]
            duplicate = next((key for key in keys if keys.count(key) > 1), None)
            if duplicate is not None:
                raise QueryValidationError(f"{source} input variable {duplicate!r} is duplicated.")
            definitions.update({d.key: d for d in sources or () if d is not None and d.key})
        return MappingProxyType(definitions)

    def __getitem__(self, selector: str) -> ViewElement:
        """The table or input with that exact component ID, else unique display name.

        Raises:
            ComponentNotFoundError: No supported element matches.
            AmbiguousComponentError: Several elements share the display name.
            ComponentVariableError: The input is not bound to a defined variable.
        """
        if not isinstance(selector, str):
            raise TypeError("View element selector must be a string ID or display name.")
        element = _find(self._elements, selector, ComponentNotFoundError,
                        AmbiguousComponentError, "Element", self._native.key)
        if isinstance(element, ViewInputHandle):
            element._check_binding()
        return element

    def _table(self, selector: str) -> ViewTableHandle:
        tables = [e for e in self._elements if isinstance(e, ViewTableHandle)]
        return _find(tables, selector, TableNotFoundError, AmbiguousTableError, "Table", self._native.key)

    def _input_values(self) -> dict[str, InputVariableValue]:
        """Current values of every KM and View-scoped input variable, read now."""
        km = self.native_km
        raw = list(km.get_variables())
        if getattr(self._native, "input_variable_definitions", None):
            # KM.get_variables() covers KM inputs only; View-scoped inputs
            # (such as date-picker endpoints) are read from the View node.
            raw += PackageManagerService.get_api_nodes_node_id_input_variables_values(
                km.client,
                self._native.id,
                ref_node_id=km.id,
                app_mode=AppMode.VIEWER if isinstance(self._native, PublishedView) else AppMode.CREATOR,
            ) or []
        definitions = self.input_definitions
        return {
            variable.key: InputVariableValue.of(variable, definitions.get(variable.key))
            for variable in raw if variable is not None
        }

    def _binder(self) -> Callable[[str], str]:
        """Bind ``${name}`` placeholders with current input values, read once if needed."""
        values: dict[str, InputVariableValue] | None = None

        def bind(expression: str) -> str:
            nonlocal values
            if not placeholders(expression):
                return expression
            if values is None:
                values = self._input_values()
            current = values
            return bind_inputs(
                expression,
                lambda name: current[name].value if name in current else None,
                {name: value.data_type for name, value in current.items()},
            )

        return bind


class ViewTableHandle(ViewElement):
    """One table of a View, running its native ``Table.get_query()``.

    The native query keeps every configured column (including hidden ones),
    filter, KM filter reference, and sorting.
    """

    _component: Table

    @property
    def component(self) -> Table:
        """The native PyCelonis table component."""
        return self._component

    def to_query(
        self, *, inherit_filters_from: Sequence[str] = (), extra_filters: Iterable[str] = ()
    ) -> QueryDefinition:
        """This table's query as a plain dictionary; nothing is executed.

        ``inherit_filters_from`` names tables (by ID or unique name) whose
        configured filters are added after this table's own; ``extra_filters``
        are complete PQL filter statements added last. ``${name}``
        placeholders are kept.
        """
        query = self._query(inherit_filters_from, extra_filters)
        return QueryDefinition(
            columns={column.name: column.query for column in query.columns},
            filters=[filter_.query for filter_ in query.filters],
            order_by=[{"pql": o.query, "ascending": o.ascending} for o in query.order_by_columns],
        )

    def rows(
        self,
        *,
        inherit_filters_from: Sequence[str] = (),
        extra_filters: Iterable[str] = (),
        limit: int | None = None,
        offset: int | None = None,
        distinct: bool = False,
    ) -> pd.DataFrame:
        """Run this table's query and return its rows.

        Filters compose as in :meth:`to_query`. Input placeholders are bound
        with the inputs' current values. Native PyCelonis errors propagate.
        """
        query = self._query(inherit_filters_from, extra_filters)
        bind = self._view._binder()
        bound = pql.PQL(
            columns=[pql.PQLColumn(name=c.name, query=bind(c.query)) for c in query.columns],
            filters=[pql.PQLFilter(query=bind(f.query)) for f in query.filters],
            order_by_columns=[
                pql.OrderByColumn(query=bind(o.query), ascending=o.ascending)
                for o in query.order_by_columns
            ],
        )
        return self._view.km._export(bound, limit=limit, offset=offset, distinct=distinct)

    def _query(self, inherit_filters_from: Sequence[str], extra_filters: Iterable[str]) -> pql.PQL:
        if isinstance(inherit_filters_from, str):
            raise QueryValidationError("inherit_filters_from must be a sequence of table names or IDs.")
        if isinstance(extra_filters, str):
            raise QueryValidationError("extra_filters must be an iterable of complete PQL filter strings.")
        query = self._component.get_query()
        names = [column.name for column in query.columns]
        duplicate = next((name for name in names if names.count(name) > 1), None)
        if duplicate is not None:
            raise QueryValidationError(f"Table {self.name!r} has duplicate column name {duplicate!r}.")
        filters = list(query.filters)
        for selector in inherit_filters_from:
            filters.extend(self._view._table(selector).component.get_filters())
        for statement in extra_filters:
            if not isinstance(statement, str) or not statement.strip():
                raise QueryValidationError("extra_filters must be non-empty PQL filter strings.")
            filters.append(pql.PQLFilter(query=statement))
        return pql.PQL(columns=query.columns, filters=filters, order_by_columns=query.order_by_columns)
