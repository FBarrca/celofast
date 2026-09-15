from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from celofast import Query, QueryValidationError
from celofast.resources.knowledge_model import KnowledgeModelHandle
from celofast.sdk import Capture, Source
from celofast.sdk.objects import Attribute, Filter, KPI
from test_sdk_generate import load_generated


def model_fixture(tmp_path, mode="draft"):
    capture = Capture.create(
        Source(tenant_id="t", space_id="s", package_id="p", key="km", mode=mode),
        {
            "dataModelId": "dm",
            "records": [{"id": "Plant", "attributes": [
                {"id": "Number", "columnType": "STRING", "pql": '"Plant"."Number"'},
            ]}],
            "kpis": [{"id": "Value", "columnType": "INTEGER", "pql": "1 + ${days}"}],
            "filters": [{"id": "Active", "pql": 'FILTER "Plant"."Age" < ${days};'}],
        },
        input_variables={"days": {"defaultValue": "30"}},
    )
    model, _ = load_generated(capture, tmp_path)
    handle = KnowledgeModelHandle(
        MagicMock(), SimpleNamespace(id="dm"), source=capture.source,
        draft=mode == "draft",
    )
    return model, handle


@pytest.mark.parametrize("mode", ["draft", "published"])
def test_connected_generated_query_uses_native_execution(tmp_path, mode):
    model, handle = model_fixture(tmp_path, mode)
    km = handle
    assert km is not model
    assert not hasattr(model, "_handle")
    assert not hasattr(model, "select")
    assert km.native is handle.native
    assert km.data_model is handle.data_model
    assert km.augmentation_tables is handle.augmentation_tables
    query = (
        km.select(plant=model.records.plant.number, value=model.kpis.value)
        .where(model.filters.active)
        .order_by(model.kpis.value.desc(), model.records.plant.number)
    )
    assert isinstance(query, Query)
    with patch("celofast.resources.knowledge_model.pql.DataFrame.from_pql") as from_pql:
        compiled = query.build(variables={"days": "30"})
        from_pql.assert_not_called()
        assert [c.name for c in compiled.columns] == ["plant", "value"]
        assert compiled.columns[1].query == "1 + 30"
        assert compiled.filters[0].query == 'FILTER "Plant"."Age" < 30;'
        assert compiled.order_by_columns[0].query == "1 + 30"
        assert compiled.order_by_columns[0].ascending is False
        assert compiled.order_by_columns[1].ascending is True
        result = query.execute(variables={"days": "7"}, limit=10, offset=2, distinct=True)
        from_pql.assert_called_once()
        assert from_pql.call_args.kwargs["saola_connector"] is handle._connector
        assert from_pql.call_args.args[0].columns[1].query == "1 + 7"
        from_pql.return_value.to_pandas.assert_called_once_with(limit=10, offset=2, distinct=True)
        assert result is from_pql.return_value.to_pandas.return_value
    assert km.build(query.to_query(), variables={"days": "30"}).columns[1].query == "1 + 30"
    with patch.object(handle, "execute") as execute:
        km.execute(query.to_query(), limit=3)
        assert execute.call_args.kwargs["limit"] == 3


def test_composition_copies_inputs_and_export_and_never_mutates_branches(tmp_path):
    model, handle = model_fixture(tmp_path)
    columns = {"Plant number": model.records.plant.number}
    base = handle.select(columns, value=model.kpis.value)
    columns.clear()
    active = base.where(model.filters.active).where("FILTER 1 = 1;")
    largest = active.order_by(model.kpis.value.desc())
    ascending = largest.order_by(model.kpis.value.asc())
    exported = largest.to_query()
    exported["columns"].clear()
    exported["filters"].clear()
    exported["order_by"][0]["ascending"] = True
    assert len(base.to_query()["columns"]) == 2
    assert base.to_query()["filters"] == []
    assert active.to_query()["order_by"] == []
    assert len(largest.to_query()["filters"]) == 2
    assert largest.to_query()["order_by"][0]["ascending"] is False
    assert ascending.to_query()["order_by"][0]["ascending"] is True
    assert largest.order_by().to_query()["order_by"] == []
    assert largest.to_query()["columns"]["value"] == model.kpis.value
    with pytest.raises(FrozenInstanceError):
        base._filters = ()


def test_raw_queries_work_without_a_generated_package(tmp_path):
    _, handle = model_fixture(tmp_path)
    compiled = handle.select({"columns": "${value}"}).where("FILTER 1 = 1;").order_by("1").build(
        variables={"value": "42"}
    )
    assert compiled.columns[0].name == "columns"
    assert compiled.columns[0].query == "42"


def test_query_rejects_invalid_shapes_and_categories(tmp_path):
    model, handle = model_fixture(tmp_path)
    base = handle.select(value="1")
    invalid = [
        lambda: handle.select(),
        lambda: handle.select(["1"]),
        lambda: handle.select({"value": "1"}, value="2"),
        lambda: handle.select({" ": "1"}),
        lambda: handle.select(value=model.filters.active),
        lambda: base.where(model.kpis.value),
        lambda: base.order_by(model.filters.active),
        lambda: base.execute(limit=-1),
    ]
    for build_invalid in invalid:
        with pytest.raises(QueryValidationError):
            build_invalid()
    assert not hasattr(model, "select")


@pytest.mark.parametrize("difference", ["tenant_id", "space_id", "package_id", "key", "mode", "data_model"])
def test_query_rejects_foreign_objects_in_every_position(tmp_path, difference):
    model, handle = model_fixture(tmp_path)
    source = model.capture.source
    layer = model.capture.to_dict()
    if difference == "data_model":
        layer["dataModelId"] = "other"
    else:
        source = source.model_copy(
            update={difference: "published" if difference == "mode" else "other"}
        )
    foreign = Capture.create(source, layer)
    column = Attribute(foreign, ("records", "Plant", "attributes", "Number"))
    kpi = KPI(foreign, ("kpis", "Value"))
    filter_ = Filter(foreign, ("filters", "Active"))
    for build_invalid in (
        lambda: handle.select(value=column),
        lambda: handle.select(value="1").where(filter_),
        lambda: handle.select(value="1").where(column.eq("DE")),
        lambda: handle.select(value="1").order_by(kpi.desc()),
    ):
        query = build_invalid()
        with pytest.raises(QueryValidationError, match="different"):
            query.build(variables={"days": "30"})
        with pytest.raises(QueryValidationError, match="different"):
            handle.build(query.to_query(), variables={"days": "30"})


def test_queries_keep_independent_snapshots(tmp_path):
    model, handle = model_fixture(tmp_path)
    old = handle.select(value=model.kpis.value)
    layer = model.capture.to_dict()
    layer["kpis"][0]["pql"] = "99"
    updated = Capture.create(model.capture.source, layer)
    new_dir = tmp_path / "new"
    new_dir.mkdir()
    new_model, _ = load_generated(updated, new_dir)
    new = handle.select(value=new_model.kpis.value)
    assert old.build(variables={"days": "30"}).columns[0].query == "1 + 30"
    assert new.build().columns[0].query == "99"


@pytest.mark.parametrize("dictionary", [False, True])
def test_execution_compiles_once_and_exports_once(tmp_path, dictionary):
    from celofast.query import query_to_pql

    model, handle = model_fixture(tmp_path)
    query = handle.select(value=model.kpis.value).where(model.filters.active)
    with (
        patch("celofast.resources.knowledge_model.query_to_pql", wraps=query_to_pql) as compile_query,
        patch("celofast.resources.knowledge_model.pql.DataFrame.from_pql") as from_pql,
    ):
        if dictionary:
            result = handle.execute(query.to_query(), variables={"days": "7"}, limit=10)
        else:
            result = query.execute(variables={"days": "7"}, limit=10)
        compile_query.assert_called_once()
        from_pql.assert_called_once()
        from_pql.return_value.to_pandas.assert_called_once_with(limit=10, offset=None, distinct=False)
        assert result is from_pql.return_value.to_pandas.return_value


@pytest.mark.parametrize("dictionary", [False, True])
def test_native_exception_identity_and_chain_survive(tmp_path, dictionary):
    _, handle = model_fixture(tmp_path)
    query = handle.select(value="1")
    cause = ValueError("upstream cause")
    error = RuntimeError("upstream export")
    error.__cause__ = cause
    with patch("celofast.resources.knowledge_model.pql.DataFrame.from_pql", side_effect=error):
        with pytest.raises(RuntimeError) as caught:
            if dictionary:
                handle.execute(query.to_query())
            else:
                query.execute()
    assert caught.value is error
    assert caught.value.__cause__ is cause


@pytest.mark.parametrize("dictionary", [False, True])
def test_invalid_captured_path_has_same_local_error(tmp_path, dictionary):
    model, handle = model_fixture(tmp_path)
    invalid = Attribute(model.capture, ("records", "missing"))
    with pytest.raises(QueryValidationError, match="captured query object"):
        if dictionary:
            handle.build({"columns": {"value": invalid}})
        else:
            handle.select(value=invalid)
