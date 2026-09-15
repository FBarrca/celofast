from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from pycelonis.errors import PyCelonisDataExportFailedError, PyCelonisQueryResolutionError
from pycelonis_core.utils.errors import PyCelonisHTTPStatusError, PyCelonisPermissionError
from saolapy.errors import DataExportFailedError

from celofast import QueryValidationError
from celofast.resources.knowledge_model import KnowledgeModelHandle
from celofast.sdk import Capture, Source
from celofast.sdk.objects import Attribute, Filter, Record
from test_sdk_generate import load_generated


@pytest.fixture
def context(tmp_path):
    capture = Capture.create(
        Source(tenant_id="t", space_id="s", package_id="p", key="inventory", mode="draft"),
        {
            "dataModelId": "dm",
            "records": [{
                "id": "O_CELONIS_PLANT", "description": "Plants in the inventory",
                "attributes": [
                    {"id": "NumberFormatted", "columnType": "STRING", "pql": '"Plant"."Number"'},
                    {"id": "Name", "columnType": "STRING", "pql": '"Plant"."Name"'},
                    {"id": "Country", "columnType": "STRING", "pql": '"Plant"."Country"'},
                    {"id": "NoPql", "columnType": "STRING"},
                    {"id": "EmptyPql", "pql": " "},
                    {"id": "NullPql", "pql": None},
                    {"id": "WrongType", "type": "KPI", "pql": "1"},
                ],
                "newAttributes": [{"id": "NewValue", "columnType": "INTEGER", "pql": "${days}"}],
                "augmentedAttributes": [{"id": "AugmentedValue", "pql": "2"}],
            }],
            "filters": [{"id": "ActiveInventory", "pql": 'FILTER "Plant"."Active" = 1;'}],
        },
        input_variables={"days": {"defaultValue": "30"}},
    )
    root, _ = load_generated(capture, tmp_path)
    handle = KnowledgeModelHandle(MagicMock(), SimpleNamespace(id="dm"), source=capture.source)
    return root, handle


@pytest.fixture
def km(context):
    return context[1]


@pytest.fixture
def model(context):
    return context[0]


def test_acceptance_returns_all_record_columns_and_combines_filters(km, model):
    plant = model.records.o_celonis_plant
    all_plants = km.select(plant)
    active_plants = all_plants.where(model.filters.active_inventory)
    query = active_plants.where(plant.country.eq("DE"))
    expected_columns = ["NumberFormatted", "Name", "Country", "NewValue", "AugmentedValue"]
    assert list(query.to_query()["columns"]) == expected_columns
    assert query.to_query()["columns"]["Country"] == plant.country
    assert plant.id == "O_CELONIS_PLANT"
    assert plant.description == "Plants in the inventory"
    assert plant.metadata["attributes"][0]["id"] == "NumberFormatted"
    assert plant.number_formatted.pql == '"Plant"."Number"'
    assert all_plants.to_query()["filters"] == []
    assert len(active_plants.to_query()["filters"]) == 1
    assert len(query.to_query()["filters"]) == 2

    # Exercise the real native connector/SaolaPy path, mocking only the cloud
    # export. This verifies unlimited/distinct options and the AND filter list.
    frame = pd.DataFrame([["1000", "Berlin", "DE", 30, 2]], columns=expected_columns)
    frame.index.name = "Index"
    km.native._export_data_frame.return_value = frame.reset_index()
    result = query.execute(distinct=True, variables={"days": "30"})
    pd.testing.assert_frame_equal(result, frame)
    compiled, draft = km.native._export_data_frame.call_args.args
    assert draft is True
    assert compiled.limit is None
    assert compiled.distinct is True
    assert [c.name for c in query.build(variables={"days": "30"}).columns] == expected_columns
    assert [f.query for f in compiled.filters] == [
        'FILTER "Plant"."Active" = 1;',
        'FILTER ("Plant"."Country"\n) = \'DE\';',
    ]
    assert next(c for c in compiled.columns if c.name == "NewValue").query == "30"
    # Existing dictionary calls retain their behavior.
    km.execute({"columns": {"Plant": plant.number_formatted}})
    assert "Plant" in [c.name for c in km.native._export_data_frame.call_args.args[0].columns]


def test_explicit_aliases_and_execution_options(km, model):
    plant = model.records.o_celonis_plant
    query = km.select(plant_number=plant.number_formatted, plant_name=plant.name)
    assert list(query.to_query()["columns"]) == ["plant_number", "plant_name"]
    with patch("celofast.resources.knowledge_model.pql.DataFrame.from_pql") as from_pql:
        query.execute(limit=100, offset=0, distinct=True)
        from_pql.return_value.to_pandas.assert_called_once_with(limit=100, offset=0, distinct=True)
    with pytest.raises(QueryValidationError, match="Duplicate"):
        km.select(plant, Country=plant.country)


@pytest.mark.parametrize("option,value", [
    ("limit", -1), ("offset", -1), ("limit", True), ("offset", True),
    ("limit", 1.5), ("offset", "0"), ("distinct", 1),
])
def test_invalid_execution_options_fail_before_export(km, model, option, value):
    with pytest.raises(QueryValidationError):
        km.select(model.records.o_celonis_plant).execute(**{option: value})
    km.native._export_data_frame.assert_not_called()


@pytest.mark.parametrize("value,literal", [
    ("DE", "'DE'"), ("O'Brien", "'O\\'Brien'"),
    ("C:\\plants\\", "'C:\\\\plants\\\\'"),
    ("${missing} -- /* text */", "'${missing} -- /* text */'"),
    (42, "42"), (2.5, "2.5"), (True, "1"), (False, "0"),
    (date(2026, 9, 15), "{d '2026-09-15'}"),
    (datetime(1970, 1, 1, 0, 0, 0, 123000, tzinfo=timezone.utc), "{t 123}"),
])
def test_equality_encodes_literals_after_explicit_binding(km, model, value, literal):
    plant = model.records.o_celonis_plant
    predicate = plant.new_value.eq(value)
    query = km.select(plant).where(predicate)
    assert query.build(variables={"days": "30"}).filters[0].query == f"FILTER (30\n) = {literal};"
    assert query.build(variables={"days": "7"}).filters[0].query == f"FILTER (7\n) = {literal};"
    assert km.build(query.to_query(), variables={"days": "30"}).filters[0].query == query.build(variables={"days": "30"}).filters[0].query
    with pytest.raises(FrozenInstanceError):
        predicate._literal = "'changed'"
    with pytest.raises(QueryValidationError, match="Python and/or"):
        bool(predicate)


def test_null_predicate_and_raw_filter_compose(km, model):
    plant = model.records.o_celonis_plant
    query = km.select(plant).where(plant.country.eq(None)).where("FILTER @active_inventory;")
    assert query.build(variables={"days": "30"}).filters[0].query.endswith("IS NULL;")
    assert query.build(variables={"days": "30"}).filters[1].query == "FILTER @active_inventory;"


@pytest.mark.parametrize("value", [[], {}, object(), float("nan"), float("inf"), datetime(2026, 1, 1, microsecond=1)])
def test_invalid_literal_values(km, model, value):
    with pytest.raises(QueryValidationError):
        model.records.o_celonis_plant.country.eq(value)


def test_empty_invalid_foreign_records_and_filters(km, model):
    source = model.capture.source
    empty = Record(Capture.create(source, {"dataModelId": "dm", "attributes": []}))
    with pytest.raises(QueryValidationError, match="no queryable"):
        km.select(empty)
    with pytest.raises(QueryValidationError, match="record"):
        km.select(Record(model.capture, ("records", "missing")))
    with pytest.raises(QueryValidationError, match="captured query object"):
        km.select(model.records.o_celonis_plant).where(Filter(model.capture, ("filters", "missing")))
    with pytest.raises(QueryValidationError):
        km.select(model.records.o_celonis_plant).where(model.records.o_celonis_plant.country)
    with pytest.raises(QueryValidationError):
        km.select(model.filters.active_inventory)
    foreign = Capture.create(source.model_copy(update={"key": "other"}), model.capture.to_dict())
    foreign_record = Record(foreign, ("records", "O_CELONIS_PLANT"))
    foreign_attr = Attribute(foreign, ("records", "O_CELONIS_PLANT", "attributes", "Country"))
    for operation in (
        lambda: km.select(foreign_record),
        lambda: km.select(model.records.o_celonis_plant).where(foreign_attr.eq("DE")),
    ):
        with pytest.raises(QueryValidationError, match="different"):
            operation().build(variables={"days": "30"})


def test_duplicate_attribute_ids_across_collections_are_rejected(km, model):
    capture = Capture.create(model.capture.source, {
        "dataModelId": "dm",
        "attributes": [{"id": "Value", "pql": "1"}],
        "newAttributes": [{"id": "Value", "pql": "2"}],
    })
    with pytest.raises(QueryValidationError, match="Duplicate record attribute"):
        km.select(Record(capture))


@pytest.mark.parametrize("filter_", [
    "FILTER ('; -- /*' = '; -- /*');",
    "/* leading */ FILTER 1 = 1; -- trailing",
    'FILTER COALESCE(KPI("value"), 0) > 0;',
    'FILTER "Plant"."Country" IN (\'DE\', \'FR\');',
    'FILTER "Plant"."Country" IS NOT NULL;',
    'FILTER "Plant"."Date" >= {d \'2026-09-15\'};',
])
def test_raw_pql_is_passed_through(km, filter_):
    expression = 'CASE WHEN "Plant"."Country" = \'DE\' THEN 1 ELSE 0 END'
    native = km.select(value=expression).where(filter_).build()
    assert native.columns[0].query == expression
    assert native.filters[0].query == filter_


@pytest.mark.parametrize("text", ["SUM(", "1 +", "'unclosed", "/* unclosed", "= 1"])
def test_pql_grammar_is_delegated_to_celonis(km, text):
    query = km.select(value=text).where(text).order_by(text)
    built = query.build()
    direct = km.build(query.to_query())
    assert built.columns[0].query == direct.columns[0].query == text
    assert built.filters[0].query == direct.filters[0].query == text
    assert built.order_by_columns[0].query == text


def test_template_output_uses_same_compiler(km):
    query = km.select(value="${expression}")
    assert query.build(variables={"expression": "1 +"}).columns[0].query == "1 +"
    assert km.build(query.to_query(), variables={"expression": "1 +"}).columns[0].query == "1 +"


@pytest.mark.parametrize("cause", [
    PyCelonisQueryResolutionError("unknown filter missing"),
    PyCelonisDataExportFailedError(None, "Syntax error near FOO"),
    PyCelonisHTTPStatusError("400 Bad Request: parsing error near FOO"),
    PyCelonisHTTPStatusError("400 Bad Request: filter 'missing' not found"),
])
def test_server_query_errors_preserve_native_exceptions(km, cause):
    km.native._export_data_frame.side_effect = cause
    with pytest.raises(DataExportFailedError) as error:
        km.select(value="UNKNOWN_FUNCTION(1)").execute()
    assert error.value.__cause__ is cause


@pytest.mark.parametrize("cause", [
    PyCelonisPermissionError("Forbidden"),
    PyCelonisHTTPStatusError("503 Service unavailable"),
    PyCelonisDataExportFailedError(None, "Out of memory"),
])
def test_unrelated_server_failures_preserve_native_exceptions(km, cause):
    km.native._export_data_frame.side_effect = cause
    with pytest.raises(DataExportFailedError) as error:
        km.select(value="1").execute()
    assert error.value.__cause__ is cause
