from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pandas as pd
import pytest
from pycelonis.ems.apps.content_node.view.component import Component
from pycelonis.ems.apps.content_node.view.content import ViewContent
from pycelonis.ems.studio.content_node.view import View
from pydantic.v1 import parse_obj_as

from celofast import AmbiguousComponentError, ComponentVariableError, DateRange, DateRangeDetails
from celofast.resources.knowledge_model import KnowledgeModelConnection
from celofast.resources.view import ViewHandle
from celofast.resources.view_input import (
    DatePickerHandle,
    DropdownHandle,
    InputBoxHandle,
)


def make_handle(*, variable_key: str = "dropdown_value"):
    content = ViewContent(
        metadata={
                "key": "inputs-view",
                "name": "Inputs",
                "knowledgeModelKey": "orders-km",
            }, components=[
                {
                    "id": "search-input",
                    "type": "input-box",
                    "settings": {
                        "name": "Search",
                        "type": "string",
                        "placeholder": "Search orders",
                        "value": "${input_field}",
                        "onChange": {
                            "update": {"variables": [{"name": "input_field"}]}
                        },
                    },
                },
                {
                    "id": "region-dropdown",
                    "type": "input-dropdown",
                    "settings": {
                        "name": "Region",
                        "attribute": "regions.region-name",
                        "dataSources": [
                            {
                                "id": "regions",
                                "attributes": [
                                    {
                                        "id": "region-name",
                                        "displayName": "Region",
                                        "pql": '"Orders"."REGION"',
                                    }
                                ],
                                "filters": [
                                    {"pql": "active_regions", "isReferenced": True}
                                ],
                            }
                        ],
                        "onChange": {
                            "update": {
                                "selection": "single",
                                "variables": [{"name": variable_key}],
                            }
                        },
                    },
                },
                {
                    "id": "reporting-period",
                    "type": "date-picker",
                    "settings": {
                        "name": "Reporting period",
                        "rangeSelection": True,
                        "onChange": {
                            "update": {
                                "variables": {
                                    "endDate": "end_date",
                                    "startDate": "start_date",
                                }
                            }
                        },
                    },
                },
                {
                    "id": "multi-selector",
                    "type": "input-selector",
                    "settings": {
                        "name": "Groups",
                        "onChange": {"update": {
                            "selection": "multiple",
                            "variables": [{"name": "groups"}],
                        }},
                    },
                },
                {
                    "id": "single-date",
                    "type": "date-picker",
                    "settings": {
                        "name": "Due date",
                        "onChange": {"update": {
                            "variables": [{"name": "due_date"}],
                        }},
                    },
                },
                {
                    "id": "include-closed",
                    "type": "checkbox",
                    "settings": {
                        "name": "Include closed",
                        "onChange": {"update": {
                            "variables": [{"name": "include_closed"}],
                        }},
                    },
                },
            ]
    )
    api_client = MagicMock()

    class ParsingClient:
        """Parses responses into the requested PyCelonis models, like the real client."""

        def request(self, **kwargs):
            return parse_obj_as(kwargs["type_"], api_client.request(**kwargs))

    native_km = SimpleNamespace(
        id="km-id",
        key="orders-km",
        client=ParsingClient(),
        input_variable_definitions=[
            SimpleNamespace(
                key="input_field",
                data_type="TEXT",
                default_value="",
                display_name="Search text",
                description="Text entered in the search box",
                propagate=False,
                scope="USER_SPECIFIC",
            ),
            SimpleNamespace(
                key="dropdown_value",
                data_type="TEXT",
                default_value="All",
                display_name="Region",
                description="Selected region",
                propagate=False,
                scope="USER_SPECIFIC",
            ),
            SimpleNamespace(
                key="start_date",
                data_type="DATE",
                default_value="2026-09-01",
                display_name="Start date",
                description=None,
                propagate=False,
                scope="USER_SPECIFIC",
            ),
            SimpleNamespace(
                key="end_date",
                data_type="DATE",
                default_value="2026-09-30",
                display_name="End date",
                description=None,
                propagate=False,
                scope="USER_SPECIFIC",
            ),
            SimpleNamespace(key="groups", data_type="TEXT", default_value="[]"),
            SimpleNamespace(key="due_date", data_type="DATE", default_value=None),
            SimpleNamespace(key="include_closed", data_type="BOOLEAN", default_value="false"),
        ],
    )

    def get_variables():
        response = api_client.request(
            method="GET",
            url="/package-manager/api/nodes/km-id/input-variables/values",
            params={},
            parse_json=True,
            type_=Any,
        )
        return [
            SimpleNamespace(
                key=item["key"],
                data_type=item.get("dataType"),
                default_value=item.get("defaultValue"),
                value=item.get("value"),
                value_or_default=item.get("valueOrDefault"),
                display_name=item.get("displayName"),
                description=item.get("description"),
                scope=item.get("scope"),
                propagate=item.get("propagate"),
            )
            for item in response
        ]

    native_km.get_variables = get_variables
    km = MagicMock(spec=KnowledgeModelConnection)
    km.native = native_km
    km.mode = "draft"
    native_view = SimpleNamespace(
        id="view-id",
        key="inputs-view",
        input_variable_definitions=[],
    )
    view = ViewHandle(cast(View, native_view), content, lambda: km)
    return view, km, api_client


def test_discovers_explicit_input_component_types_and_properties():
    view, _, _ = make_handle()

    input_box = view["Search"]
    assert input_box is view.elements[0]
    assert input_box.input_type == "string"
    assert input_box.placeholder == "Search orders"
    assert input_box.variable_key == "input_field"
    assert input_box.variable_definition.scope == "USER_SPECIFIC"

    dropdown = view["region-dropdown"]
    assert dropdown is view.elements[1]
    assert dropdown.name == "Region"
    assert dropdown.selection_mode == "single"
    assert dropdown.variable_key == "dropdown_value"
    assert dropdown.data_source_id == "regions"
    assert dropdown.attribute_id == "region-name"
    assert dropdown.attribute_pql == '"Orders"."REGION"'

    date_picker = view["Reporting period"]
    assert date_picker is view.elements[2]
    assert date_picker.range_selection is True
    assert date_picker.start_variable_key == "start_date"
    assert date_picker.end_variable_key == "end_date"


def test_date_range_uses_one_value_request_and_decodes_iso_dates():
    view, _, api_client = make_handle()
    api_client.request.return_value = [
        {"key": "start_date", "valueOrDefault": "2026-09-01"},
        {"key": "end_date", "valueOrDefault": "2026-09-14"},
    ]

    assert view["Reporting period"].value == DateRange(
        start=pd.Timestamp("2026-09-01").date(),
        end=pd.Timestamp("2026-09-14").date(),
    )
    assert api_client.request.call_count == 1


def test_component_value_uses_view_node_and_km_reference():
    view, _, api_client = make_handle()
    api_client.request.return_value = [
        {
            "key": "dropdown_value",
            "dataType": "TEXT",
            "defaultValue": "All",
            "value": "EMEA",
            "valueOrDefault": "EMEA",
            "scope": "USER_SPECIFIC",
        }
    ]

    assert view["Region"].value == "EMEA"
    api_client.request.assert_called_once_with(
        method="GET",
        url="/package-manager/api/nodes/km-id/input-variables/values",
        params={},
        parse_json=True,
        type_=Any,
    )


def test_published_view_input_uses_viewer_mode():
    view, km, api_client = make_handle()
    km.mode = "published"
    api_client.request.return_value = [
        {"key": "input_field", "valueOrDefault": "published value"}
    ]

    assert view["Search"].value == "published value"
    assert api_client.request.call_args.kwargs == {
        "method": "GET",
        "url": "/package-manager/api/nodes/km-id/input-variables/values",
        "params": {},
        "parse_json": True,
        "type_": Any,
    }


def test_dropdown_options_execute_distinct_native_attribute_query():
    view, km, _ = make_handle()
    km._export.return_value = pd.DataFrame(
        {"value": ["EMEA", "AMER", None]}
    )

    options = view["Region"].options(limit=25, offset=5)

    assert [(item.value, item.label) for item in options] == [
        ("EMEA", "EMEA"),
        ("AMER", "AMER"),
    ]
    query = km._export.call_args.args[0]
    assert [(c.name, c.query) for c in query.columns] == [("value", '"Orders"."REGION"')]
    assert [f.query for f in query.filters] == ["FILTER @active_regions;"]
    assert km._export.call_args.kwargs == {"limit": 25, "offset": 5, "distinct": True}


def test_control_binding_must_reference_a_km_variable():
    view, _, _ = make_handle(variable_key="missing_variable")

    with pytest.raises(ComponentVariableError, match="missing_variable"):
        view["Region"]


def test_unbound_input_box_fails_when_selected():
    view, _, _ = make_handle()
    unbound = InputBoxHandle(
        view,
        Component(
            id="unbound-input",
            type="input-box",
            settings={"type": "string"},
        ),
        tab_name=None,
    )
    view._elements = (*view.elements, unbound)

    with pytest.raises(
        ComponentVariableError,
        match="must bind exactly one input variable",
    ):
        view["unbound-input"]


def test_input_value_is_fetched_fresh_each_time():
    view, _, api_client = make_handle()
    api_client.request.side_effect = [
        [{"key": "input_field", "valueOrDefault": "first"}],
        [{"key": "input_field", "valueOrDefault": "second"}],
    ]
    search = view["Search"]

    assert search.value == "first"
    assert search.value == "second"
    assert api_client.request.call_count == 2


def test_input_details_include_assignment_default_and_metadata():
    view, _, api_client = make_handle()
    api_client.request.return_value = [
        {"key": "input_field", "value": "needle", "valueOrDefault": "needle"}
    ]

    details = view["Search"].details()

    assert (details.assigned_value, details.default_value, details.value) == (
        "needle", "", "needle"
    )
    assert details.display_name == "Search text"
    assert details.scope == "USER_SPECIFIC"


def test_range_details_read_both_variables_in_one_request():
    view, _, api_client = make_handle()
    api_client.request.return_value = [
        {"key": "start_date", "valueOrDefault": "2026-09-01"},
        {"key": "end_date", "value": "2026-09-14"},
    ]

    details = view["Reporting period"].details()

    assert isinstance(details, DateRangeDetails)
    assert details.start.default_value == "2026-09-01"
    assert details.end.assigned_value == "2026-09-14"
    api_client.request.assert_called_once()


def test_selector_single_date_and_checkbox_decode_independently():
    from datetime import date

    view, _, api_client = make_handle()
    api_client.request.return_value = [
        {"key": "groups", "valueOrDefault": '["A", "B"]'},
        {"key": "due_date", "valueOrDefault": "2026-09-24"},
        {"key": "include_closed", "valueOrDefault": "true"},
    ]

    assert view["Groups"].value == ("A", "B")
    assert view["Due date"].value == date(2026, 9, 24)
    assert view["Include closed"].value is True
    assert api_client.request.call_count == 3


def test_names_collide_across_element_types_and_ids_win():
    from celofast.resources.view import ViewTableHandle

    view, _, _ = make_handle()
    component = ViewContent(
        metadata={"key": "other", "name": "Other", "knowledgeModelKey": "orders-km"},
        components=[{"id": "table-orders", "type": "table", "settings": {
            "name": "Search", "dataSources": [],
        }}],
    ).components[0]
    real_table = ViewTableHandle(view, component, tab_name="Second tab")
    view._elements = (*view.elements, real_table)

    with pytest.raises(AmbiguousComponentError, match="Second tab"):
        view["Search"]
    assert view["search-input"].id == "search-input"
    assert view["table-orders"] is real_table


def test_view_scoped_date_picker_variables_read_and_decode_epoch_dates():
    from datetime import datetime, timezone

    view, _, api_client = make_handle()
    view.native.input_variable_definitions = [
        SimpleNamespace(key="view_start", data_type="DATE", default_value="1758067200000"),
        SimpleNamespace(key="view_end", data_type="DATE", default_value="1797465600000"),
    ]
    component = Component(
        id="view-range",
        type="date-picker",
        settings={
            "rangeSelection": True,
            "onChange": {"update": {"variables": {
                "startDate": "view_start",
                "endDate": "view_end",
            }}},
        },
    )
    date_picker = DatePickerHandle(view, component, tab_name=None)
    view._elements = (*view.elements, date_picker)

    km_values = [{"key": "dropdown_value", "dataType": "TEXT", "valueOrDefault": "EMEA"}]
    view_values = [
        {
            "key": "view_start", "dataType": "DATE", "defaultValue": "1758067200000",
            "value": None, "valueOrDefault": "1758067200000",
        },
        {
            "key": "view_end", "dataType": "DATE", "defaultValue": "1797465600000",
            "value": "1797465600000", "valueOrDefault": "1797465600000",
        },
    ]
    api_client.request.side_effect = [km_values, view_values]

    assert view["view-range"].value == DateRange(
        start=datetime.fromtimestamp(1758067200, tz=timezone.utc).date(),
        end=datetime.fromtimestamp(1797465600, tz=timezone.utc).date(),
    )
    assert api_client.request.call_count == 2
    view_call = api_client.request.call_args_list[1].kwargs
    assert view_call["url"] == "/package-manager/api/nodes/view-id/input-variables/values"
    assert view_call["params"]["refNodeId"] == "km-id"
    assert view_call["params"]["appMode"].value == "CREATOR"


def test_view_scoped_date_picker_value_is_fetched_fresh_each_time():
    from datetime import datetime, timezone

    view, _, api_client = make_handle()
    view.native.input_variable_definitions = [
        SimpleNamespace(key="view_start", data_type="DATE", default_value="1758067200000"),
        SimpleNamespace(key="view_end", data_type="DATE", default_value="1797465600000"),
    ]
    component = Component(
        id="view-range-fresh",
        type="date-picker",
        settings={
            "rangeSelection": True,
            "onChange": {"update": {"variables": {
                "startDate": "view_start",
                "endDate": "view_end",
            }}},
        },
    )
    date_picker = DatePickerHandle(view, component, tab_name=None)
    view._elements = (*view.elements, date_picker)

    def response(start: str):
        return [
            {"key": "view_start", "data_type": "DATE", "value_or_default": start},
            {
                "key": "view_end",
                "data_type": "DATE",
                "value_or_default": "1797465600000",
            },
        ]

    view_responses = iter([response("1758067200000"), response("1758153600000")])

    def get_values(*args, **kwargs):
        if kwargs["url"].startswith("/package-manager/api/nodes/view-id/"):
            return next(view_responses)
        return []

    api_client.request.side_effect = get_values
    first = date_picker.value
    second = date_picker.value

    assert first.start == datetime.fromtimestamp(1758067200, tz=timezone.utc).date()
    assert second.start == datetime.fromtimestamp(1758153600, tz=timezone.utc).date()
    assert api_client.request.call_count == 4


def test_manual_dropdown_reads_primary_view_variable_and_lists_options():
    view, _, api_client = make_handle()
    view.native.input_variable_definitions = [
        SimpleNamespace(
            key="policy_choice", data_type="TEXT", default_value="sS",
            display_name="Inventory policy", description=None, scope="VIEW",
            propagate=False,
        ),
        SimpleNamespace(
            key="show_safety_stock", data_type="BOOLEAN", default_value="true",
            display_name=None, description=None, scope="VIEW", propagate=False,
        ),
    ]
    component = Component(
        id="policy-choice",
        type="input-dropdown",
        settings={
            "variables": [{"name": "policy_choice"}, {"name": "show_safety_stock"}],
            "items": [
                {
                    "id": "policy-s",
                    "displayName": "Reorder point S",
                    "onClick": {"update": {"variables": [
                        {"name": "policy_choice", "value": "sS"},
                        {"name": "show_safety_stock", "value": "true"},
                    ]}},
                },
                {
                    "id": "policy-q",
                    "displayName": "Fixed quantity Q",
                    "onClick": {"update": {"variables": [
                        {"name": "policy_choice", "value": "sQ"},
                        {"name": "show_safety_stock", "value": "false"},
                    ]}},
                },
            ],
        },
    )
    dropdown = DropdownHandle(view, component, tab_name=None)
    view._elements = (*view.elements, dropdown)
    api_client.request.side_effect = [
        [],
        [{
            "key": "policy_choice", "dataType": "TEXT", "defaultValue": "sS",
            "value": "sQ", "valueOrDefault": "sQ", "scope": "VIEW",
        }, {
            "key": "show_safety_stock", "dataType": "BOOLEAN", "defaultValue": "true",
            "value": "false", "valueOrDefault": "false", "scope": "VIEW",
        }],
    ]

    assert view["policy-choice"].variable_keys == (
        "policy_choice", "show_safety_stock"
    )
    assert dropdown.variable_key == "policy_choice"
    assert [(item.value, item.label) for item in dropdown.options()] == [
        ("sS", "Reorder point S"),
        ("sQ", "Fixed quantity Q"),
    ]
    assert view["policy-choice"].value == "sQ"
