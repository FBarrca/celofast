from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
from pycelonis.ems.apps.content_node.view.content import ViewContent
from pycelonis.ems.studio.content_node.view import View

from celofast import AmbiguousTableError, QueryValidationError, TableNotFoundError
from celofast.resources.knowledge_model import KnowledgeModelHandle
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


def make_view_handle(*, duplicate_name: bool = False):
    native = SimpleNamespace(
        key="operations-view",
        input_variable_definitions=[
            SimpleNamespace(key="days", default_value="30")
        ],
    )
    km = MagicMock(spec=KnowledgeModelHandle)
    handle = ViewHandle(
        cast(View, native),
        make_content(duplicate_name=duplicate_name),
        lambda: km,
        variables={"region": "'EMEA'"},
    )
    return handle, km


def test_tables_are_discovered_at_root_and_inside_tabs():
    view, _ = make_view_handle()

    assert [(table.id, table.name, table.tab_name) for table in view.tables] == [
        ("table-orders", "Orders", None),
        ("table-events", "Events", "Details"),
    ]
    assert view.table("Orders") is view.tables[0]
    assert view.table("table-events") is view.tables[1]


def test_native_table_query_preserves_hidden_attributes_filter_refs_and_sorting():
    view, _ = make_view_handle()

    query = view.table("Orders").to_query()

    assert query == {
        "columns": {
            "Case ID": '"Orders"."ID"',
            "Value": 'KPI("order_value")',
        },
        "filters": ["FILTER @active_orders;"],
        "order_by": [{"pql": 'KPI("order_value")', "ascending": False}],
    }


def test_table_execution_merges_variables_and_composes_filters():
    view, km = make_view_handle()
    expected = object()
    km.execute.return_value = expected

    result = view.table("Orders").execute(
        inherit_filters_from=("Events",),
        extra_filters=('FILTER "Orders"."VALID" = 1;',),
        variables={"days": "7"},
        limit=10,
    )

    assert result is expected
    query = km.execute.call_args.args[0]
    assert query["filters"] == [
        "FILTER @active_orders;",
        "FILTER ${days} > 0;",
        'FILTER "Orders"."VALID" = 1;',
    ]
    assert km.execute.call_args.kwargs == {
        "variables": {"days": "7", "region": "'EMEA'"},
        "limit": 10,
        "offset": None,
        "distinct": False,
    }


def test_duplicate_names_require_component_id():
    view, _ = make_view_handle(duplicate_name=True)

    with pytest.raises(AmbiguousTableError, match="table-orders"):
        view.table("Orders")

    assert view.table("table-events").id == "table-events"


def test_unknown_table_has_specific_error():
    view, _ = make_view_handle()

    with pytest.raises(TableNotFoundError, match="Missing"):
        view.table("Missing")


def test_filter_composition_rejects_accidental_bare_strings():
    view, _ = make_view_handle()

    with pytest.raises(QueryValidationError, match="inherit_filters_from"):
        view.table("Orders").to_query(inherit_filters_from="Events")

    with pytest.raises(QueryValidationError, match="extra_filters"):
        view.table("Orders").to_query(extra_filters="FILTER @active;")
