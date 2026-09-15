from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pandas as pd
import pytest
from pycelonis.ems.apps.content_node.view.component import Component
from pycelonis.ems.apps.content_node.view.content import ViewContent
from pycelonis.ems.studio.content_node.view import View

from celofast import ComponentVariableError, DateRange
from celofast.resources.knowledge_model import KnowledgeModelHandle
from celofast.resources.view import ViewHandle
from celofast.resources.view_input import InputBoxHandle


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
            ]
    )
    api_client = MagicMock()
    native_km = SimpleNamespace(
        id="km-id",
        key="orders-km",
        client=api_client,
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
        ],
    )
    km = MagicMock(spec=KnowledgeModelHandle)
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

    input_box = view.input_box("Search")
    assert input_box is view.input_boxes[0]
    assert input_box.input_type == "string"
    assert input_box.placeholder == "Search orders"
    assert input_box.variable_key == "input_field"
    assert input_box.scope == "USER_SPECIFIC"

    dropdown = view.dropdown("region-dropdown")
    assert dropdown is view.dropdowns[0]
    assert dropdown.name == "Region"
    assert dropdown.selection_mode == "single"
    assert dropdown.variable_key == "dropdown_value"
    assert dropdown.data_source_id == "regions"
    assert dropdown.attribute_id == "region-name"
    assert dropdown.attribute_pql == '"Orders"."REGION"'

    date_picker = view.date_picker("Reporting period")
    assert date_picker is view.date_pickers[0]
    assert date_picker.range_selection is True
    assert date_picker.start_variable_key == "start_date"
    assert date_picker.end_variable_key == "end_date"


def test_date_range_uses_one_value_request_and_decodes_iso_dates():
    view, _, api_client = make_handle()
    api_client.request.return_value = [
        {"key": "start_date", "valueOrDefault": "2026-09-01"},
        {"key": "end_date", "valueOrDefault": "2026-09-14"},
    ]

    assert view.date_picker("Reporting period").get() == DateRange(
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

    assert view.dropdown("Region").get() == "EMEA"
    api_client.request.assert_called_once_with(
        method="GET",
        url="/package-manager/api/nodes/view-id/input-variables/values",
        params={"refNodeId": "km-id", "appMode": "CREATOR"},
        parse_json=True,
        type_=Any,
    )


def test_dropdown_options_execute_distinct_native_attribute_query():
    view, km, _ = make_handle()
    km.execute.return_value = pd.DataFrame(
        {"value": ["EMEA", "AMER", None]}
    )

    options = view.dropdown("Region").options(limit=25, offset=5)

    assert [(item.value, item.label) for item in options] == [
        ("EMEA", "EMEA"),
        ("AMER", "AMER"),
    ]
    km.execute.assert_called_once_with(
        {
            "columns": {"value": '"Orders"."REGION"'},
            "filters": ["FILTER @active_regions;"],
        },
        limit=25,
        offset=5,
        distinct=True,
    )


def test_control_binding_must_reference_a_km_variable():
    view, _, _ = make_handle(variable_key="missing_variable")

    with pytest.raises(ComponentVariableError, match="missing_variable"):
        view.dropdown("Region")


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
    view._controls = (*view.controls, unbound)

    with pytest.raises(
        ComponentVariableError,
        match="must bind exactly one Knowledge Model input variable",
    ):
        view.input_box("unbound-input")
