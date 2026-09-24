from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
from pycelonis.ems.apps.content_node.view.content import ViewContent
from pycelonis.ems.studio.content_node.view import View

from celofast import (
    AmbiguousComponentError,
    ComponentNotFoundError,
    QueryValidationError,
    UnresolvedVariableError,
)
from celofast.resources.knowledge_model import KnowledgeModelConnection
from celofast.resources.view import ViewHandle


def make_content(*, duplicate_name: bool = False) -> ViewContent:
    second_name = "Orders" if duplicate_name else "Events"
    return ViewContent(
        **{
            "metadata": {
                "key": "operations-view",
                "name": "Operations",
                "knowledgeModelKey": "orders-km",
            },
            "components": [
                {
                    "id": "table-orders",
                    "type": "table",
                    "settings": {
                        "name": "Orders",
                        "dataSources": [
                            {
                                "id": "orders-source",
                                "attributes": [
                                    {
                                        "id": "case-id",
                                        "displayName": "Case ID",
                                        "pql": '"Orders"."ID"',
                                    },
                                    {
                                        "id": "value",
                                        "displayName": "Value",
                                        "pql": 'KPI("order_value")',
                                        "hide": True,
                                    },
                                ],
                                "filters": [
                                    {"pql": "active_orders", "isReferenced": True}
                                ],
                            }
                        ],
                        "data": {
                            "sortBy": [
                                {
                                    "id": "sort-value",
                                    "field": "value",
                                    "order": 100,
                                    "direction": "DESC",
                                }
                            ]
                        },
                    },
                }
            ],
            "tabs": [
                {
                    "id": "details-tab",
                    "name": "Details",
                    "components": [
                        {
                            "id": "table-events",
                            "type": "table",
                            "settings": {
                                "name": second_name,
                                "dataSources": [
                                    {
                                        "id": "events-source",
                                        "attributes": [
                                            {
                                                "id": "activity",
                                                "displayName": "Activity",
                                                "pql": '"Events"."ACTIVITY"',
                                            }
                                        ],
                                        "filters": [
                                            {
                                                "pql": "FILTER ${days} > 0;",
                                                "isReferenced": False,
                                            }
                                        ],
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    )


def make_view_handle(*, duplicate_name: bool = False, days: str | None = "30"):
    native = SimpleNamespace(key="operations-view", input_variable_definitions=[])
    native_km = SimpleNamespace(
        key="orders-km",
        input_variable_definitions=[SimpleNamespace(key="days", data_type="NUMBER", default_value=days)],
        get_variables=MagicMock(return_value=[SimpleNamespace(
            key="days", data_type="NUMBER", default_value=days, value=None, value_or_default=days,
        )]),
    )
    km = MagicMock(spec=KnowledgeModelConnection)
    km.native = native_km
    handle = ViewHandle(cast(View, native), make_content(duplicate_name=duplicate_name), lambda: km)
    return handle, km


def test_tables_are_discovered_at_root_and_inside_tabs():
    view, _ = make_view_handle()

    assert [(table.id, table.name, table.tab_name) for table in view.elements] == [
        ("table-orders", "Orders", None),
        ("table-events", "Events", "Details"),
    ]
    assert view["Orders"] is view.elements[0]
    assert view["table-events"] is view.elements[1]


def test_native_table_query_preserves_hidden_attributes_filter_refs_and_sorting():
    view, _ = make_view_handle()

    query = view["Orders"].to_query()

    assert query == {
        "columns": {
            "Case ID": '"Orders"."ID"',
            "Value": 'KPI("order_value")',
        },
        "filters": ["FILTER @active_orders;"],
        "order_by": [{"pql": 'KPI("order_value")', "ascending": False}],
    }


def test_rows_compose_filters_and_bind_current_input_values():
    view, km = make_view_handle(days="7")
    expected = object()
    km._export.return_value = expected

    result = view["Orders"].rows(
        inherit_filters_from=("Events",),
        extra_filters=('FILTER "Orders"."VALID" = 1;',),
        limit=10,
    )

    assert result is expected
    query = km._export.call_args.args[0]
    assert [f.query for f in query.filters] == [
        "FILTER @active_orders;",
        "FILTER 7 > 0;",  # ${days}, read from the KM when the query runs
        'FILTER "Orders"."VALID" = 1;',
    ]
    assert [c.query for c in query.columns] == ['"Orders"."ID"', 'KPI("order_value")']
    assert km._export.call_args.kwargs == {"limit": 10, "offset": None, "distinct": False}
    # Composition applies to that read only.
    assert view["Orders"].to_query()["filters"] == ["FILTER @active_orders;"]


def test_inputs_are_read_only_when_a_query_uses_them():
    view, km = make_view_handle()
    view["Orders"].rows()
    km.native.get_variables.assert_not_called()


def test_an_input_without_a_value_fails_before_the_query():
    view, km = make_view_handle(days=None)
    with pytest.raises(UnresolvedVariableError, match=r"\$\{days\}"):
        view["Events"].rows()
    km._export.assert_not_called()


def test_duplicate_names_require_component_id():
    view, _ = make_view_handle(duplicate_name=True)

    with pytest.raises(AmbiguousComponentError, match="table-orders"):
        view["Orders"]

    assert view["table-events"].id == "table-events"


def test_unknown_table_has_specific_error():
    view, _ = make_view_handle()

    with pytest.raises(ComponentNotFoundError, match="Missing"):
        view["Missing"]


def test_filter_composition_rejects_accidental_bare_strings():
    view, _ = make_view_handle()

    with pytest.raises(QueryValidationError, match="inherit_filters_from"):
        view["Orders"].to_query(inherit_filters_from="Events")

    with pytest.raises(QueryValidationError, match="extra_filters"):
        view["Orders"].to_query(extra_filters="FILTER @active;")


def test_rows_preserves_pagination_distinct_and_dataframe():
    import pandas as pd

    view, km = make_view_handle()
    expected = pd.DataFrame({"Case ID": ["O-1"]})
    km._export.return_value = expected

    assert view["Orders"].rows(limit=1, offset=2, distinct=True).equals(expected)
    assert km._export.call_args.kwargs == {"limit": 1, "offset": 2, "distinct": True}


def test_duplicate_native_column_names_are_rejected():
    from saolapy.pql.base import PQL, PQLColumn

    view, _ = make_view_handle()
    table = view["Orders"]
    duplicate = PQL(columns=[PQLColumn(name="id", query="1"), PQLColumn(name="id", query="2")])
    object.__setattr__(table, "_component", SimpleNamespace(id="table-orders", settings=SimpleNamespace(name="Orders"), get_query=lambda: duplicate))
    with pytest.raises(QueryValidationError, match="duplicate column"):
        table.to_query()
