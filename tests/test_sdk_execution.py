from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pycelonis.pql.saola_connector import KnowledgeModelSaolaConnector

from celofast import QueryValidationError
from celofast.resources.knowledge_model import KnowledgeModelHandle
from celofast.sdk import Capture, Source
from celofast.sdk.objects import (
    KPI,
    Attribute,
    Filter,
    GenericKnowledgeObject,
    KnowledgeModel,
)


def setup_capture(mode="draft", expression='"Plant"."Number"'):
    source = Source(
        tenant_id="tenant",
        space_id="space",
        package_id="package",
        key="inventory-km",
        mode=mode,
    )
    capture = Capture.create(
        source,
        {
            "tenantId": "tenant",
            "dataModelId": "dm",
            "metadata": {"key": source.key},
            "records": [
                {
                    "id": "Plant",
                    "attributes": [
                        {"id": "Number", "pql": expression, "columnType": "string"}
                    ],
                }
            ],
            "kpis": [
                {"id": "A", "pql": 'KPI("B")'},
                {"id": "B", "pql": 'SUM("Plant"."Amount")'},
            ],
            "filters": [{"id": "Active", "pql": 'FILTER "Plant"."Active" = 1;'}],
            "variables": [{"id": "days", "value": "30"}],
        },
    )
    return capture, Attribute[str](capture, ("records", 0, "attributes", 0))


@pytest.mark.parametrize("mode", ["draft", "published"])
def test_generated_queries_use_native_connector(mode):
    capture, attribute = setup_capture(mode)
    native = MagicMock()
    dm = SimpleNamespace(id="dm")
    handle = KnowledgeModelHandle(
        native, dm, draft=mode == "draft", source=capture.source
    )
    assert handle.bind(KnowledgeModel(capture)) is handle
    query = {
        "columns": {"Plant": attribute, "Total": KPI(capture, ("kpis", 0)), "Raw": "1"},
        "filters": [Filter(capture, ("filters", 0))],
        "order_by": [{"pql": attribute}],
    }
    with patch("celofast.resources.knowledge_model.pql.DataFrame.from_pql") as from_pql:
        handle.execute(query, limit=7)
        compiled = from_pql.call_args.args[0]
        connector = from_pql.call_args.kwargs["saola_connector"]
        assert connector is handle._connector
        assert isinstance(connector, KnowledgeModelSaolaConnector)
        connector._export_data(compiled)
    native._export_data_frame.assert_called_once_with(compiled, mode == "draft")
    native.client.request.assert_not_called()
    assert compiled.columns[1].query == 'KPI("B")'
    assert compiled.filters[0].query == 'FILTER "Plant"."Active" = 1;'
    assert compiled.order_by_columns[0].query == attribute.pql


def test_generated_variables_use_captured_values_or_explicit_overrides():
    capture, attribute = setup_capture(expression='"Plant"."Value" + ${days}')
    handle = KnowledgeModelHandle(MagicMock(), SimpleNamespace(id="dm"))
    query = {"columns": {"value": attribute}, "order_by": [{"pql": attribute}]}
    compiled = handle.build(query)
    assert compiled.columns[0].query == '"Plant"."Value" + 30'
    assert compiled.order_by_columns[0].query == '"Plant"."Value" + 30'
    compiled = handle.build(query, variables={"days": "7"})
    assert compiled.columns[0].query == '"Plant"."Value" + 7'


def test_input_defaults_bind_columns_filters_and_ordering_without_mutating_capture():
    capture, _ = setup_capture(expression='"Plant"."Value" + ${days} + ${months}')
    layer = capture.to_dict()
    layer["filters"][0]["pql"] = 'FILTER "Plant"."Value" > ${months};'
    capture = Capture.create(
        capture.source,
        layer,
        input_variables={
            "days": {"defaultValue": "3"},
            "months": {"defaultValue": "12"},
        },
    )
    attribute = Attribute(capture, ("records", 0, "attributes", 0))
    handle = KnowledgeModelHandle(MagicMock(), SimpleNamespace(id="dm"))
    query = {
        "columns": {"value": attribute},
        "filters": [Filter(capture, ("filters", 0))],
        "order_by": [{"pql": attribute}],
    }
    compiled = handle.build(query, variables={"days": "7"})
    assert compiled.columns[0].query == '"Plant"."Value" + 7 + 12'
    assert compiled.order_by_columns[0].query == compiled.columns[0].query
    assert compiled.filters[0].query == 'FILTER "Plant"."Value" > 12;'
    assert "${months}" in attribute.pql
    assert capture.input_variables["days"]["defaultValue"] == "3"


def test_missing_input_default_fails_before_execution_and_raw_strings_stay_explicit():
    capture, _ = setup_capture(expression="${missing}")
    capture = Capture.create(
        capture.source,
        capture.to_dict(),
        input_variables={
            "missing": {"defaultValue": None},
        },
    )
    attribute = Attribute(capture, ("records", 0, "attributes", 0))
    handle = KnowledgeModelHandle(MagicMock(), SimpleNamespace(id="dm"))
    with pytest.raises(QueryValidationError, match="missing"):
        handle.build({"columns": {"value": attribute}})
    assert (
        handle.build({"columns": {"value": attribute}}, variables={"missing": "5"})
        .columns[0]
        .query
        == "5"
    )
    with pytest.raises(QueryValidationError, match="days"):
        handle.build(
            {"columns": {"generated": attribute, "raw": "${days}"}},
            variables={"missing": "5"},
        )


def test_generated_query_rejects_wrong_categories():
    capture, attribute = setup_capture()
    handle = KnowledgeModelHandle(MagicMock(), SimpleNamespace(id="dm"))
    for query in (
        {"columns": {"one": GenericKnowledgeObject(capture, ())}},
        {"columns": {"one": attribute}, "filters": [attribute]},
    ):
        with pytest.raises(QueryValidationError):
            handle.build(query)


def test_bind_rejects_different_data_model():
    capture, _ = setup_capture()
    handle = KnowledgeModelHandle(
        SimpleNamespace(), SimpleNamespace(id="other"), source=capture.source
    )
    with pytest.raises(QueryValidationError, match="Data Model"):
        handle.bind(KnowledgeModel(capture))
