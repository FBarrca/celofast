"""Missing or incorrect KM types are resolved from schemas, never sample values."""

import io
from datetime import datetime
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from celofast.resources.knowledge_model import KnowledgeModelConnection
from celofast.sdk import Capture
from celofast.sdk.generate import generate
from celofast.sdk.mapping import normalize
from celofast.sdk.validation import resolve_types, validate

from objects_fixture import SOURCE, attribute, load


def capture():
    return Capture.create(SOURCE, {"records": [{
        "id": "O_PLANT", "pql": "o_Plant", "identifier": {"pql": '"o_Plant"."ID"'},
        "attributes": [
            attribute("ID", '"o_Plant"."ID"'),
            attribute("Total", '"o_Plant"."Planned" + "o_Plant"."Purchased"', None),
            attribute("Planned", "COALESCE(PU_SUM(\"o_Plant\", \"o_Order\".\"Quantity\", DAYS_BETWEEN(TODAY(), \"o_Order\".\"Due\") < ${months}), 0.0)", None),
        ],
    }]}, input_variables={"months": {"dataType": "NUMBER", "defaultValue": 3}},
        tables={"o_Plant": {"primary_key": ["ID"], "columns": {"ID": "STRING"}}})


@pytest.mark.parametrize("expression", [
    'ADD_HOURS("o_Line"."LastGoodsIssueDate", COALESCE("o_Line"."TransitDurationDays" * 24, 0))',
    '"o_Line"."CalculatedDate"',  # A reference absent from the physical column catalog.
])
def test_incorrect_declared_type_is_corrected_before_validation_and_generation(tmp_path, expression):
    original = Capture.create(SOURCE, {"records": [{
        "id": "O_LINE", "pql": "o_Line", "attributes": [
            attribute("ID", '"o_Line"."ID"'),
            attribute("ActualDeliveryTimestamp", expression, "STRING"),
        ],
    }]}, tables={"o_Line": {"primary_key": ["ID"], "columns": {"ID": "STRING"}}})

    def describe(pql):
        assert pql == expression
        return "datetime"

    cap = resolve_types(original, describe)
    assert cap.definition_json == original.definition_json
    cap = Capture.model_validate_json(cap.to_json())
    assert validate(cap, lambda expressions, limit: [("L1", datetime(2024, 3, 28)), ("L2", None)]) == {}
    for name, content in generate(cap).items():
        (tmp_path / name).write_bytes(content)
    sdk = load(tmp_path, "corrected_type_sdk")
    assert sdk.Line.fields.actual_delivery_timestamp.value_type == "datetime"
    overridden = normalize(cap, {"objects": {"O_LINE": {"types": {"ActualDeliveryTimestamp": "date"}}}})
    assert overridden.objects[0].fields[1].value_type == "date"


def test_runtime_inputs_keep_declared_types_without_schema_queries():
    original = Capture.create(SOURCE, {"records": [{
        "id": "O_LINE", "pql": "o_Line", "attributes": [
            attribute("ID", '"o_Line"."ID"'),
            attribute("Value", "${choice}", "STRING"),
        ],
    }]}, tables={"o_Line": {"primary_key": ["ID"], "columns": {"ID": "STRING"}}})
    mapping = {"objects": {"O_LINE": {"include-fields": ["Value"]}}}
    cap = resolve_types(original, lambda expression: pytest.fail("Unbound input must not be probed"), mapping=mapping)
    field = normalize(cap, mapping).objects[0].fields[1]
    assert (field.value_type, field.expression) == ("str", "${choice}")


def test_missing_type_is_resolved_then_validated_and_generated(tmp_path):
    original = capture()
    described = []

    def describe(expression):
        described.append(expression)
        assert "${months}" not in expression
        assert "COALESCE" in expression
        return "float"

    cap = resolve_types(original, describe)
    assert len(described) == 1  # Direct input attributes still follow include-fields.
    assert cap.definition_json == original.definition_json
    assert cap.fingerprint == original.fingerprint
    assert original.types == {}
    cap = Capture.model_validate_json(cap.to_json())
    with pytest.raises(TypeError):
        cap.types[described[0]] = "int"

    def execute(expressions, limit):
        assert expressions[-1] == f"({described[0]}\n)"
        return [("P1", 1.25), ("P2", None)]

    assert validate(cap, execute) == {}
    for name, content in generate(cap).items():
        (tmp_path / name).write_bytes(content)
    sdk = load(tmp_path, "result_type_sdk")
    assert sdk.Plant.fields.total.value_type == "float"
    assert sdk.Plant.fields.total.expression == described[0]


@pytest.mark.parametrize("catalog", [True, False])
def test_explicit_types_and_exclusions_do_not_query_the_schema(catalog):
    def unexpected(expression):
        pytest.fail("No type lookup needed")

    for settings in ({"types": {"Total": "int"}}, {"exclude-fields": ["Total"]}):
        original = capture()
        if not catalog:
            original = original.model_copy(update={"tables_json": None})
        cap = resolve_types(original, unexpected, mapping={"objects": {"O_PLANT": settings}})
        assert cap.types == {}


def test_unresolvable_types_stay_skipped_and_export_failures_are_reported():
    cap = resolve_types(capture(), lambda expression: None)
    assert any("Total: unknown type" in message for message in normalize(cap).diagnostics)

    def broken(expression):
        raise RuntimeError("Unknown column Purchased")

    cap = resolve_types(capture(), broken)
    assert "Unknown column Purchased" in cap.validation["O_PLANT"]["Total"]
    assert any("Total: fails in Celonis" in message for message in normalize(cap).diagnostics)


@pytest.mark.parametrize("arrow_type,expected", [
    (pa.float64(), "float"), (pa.int64(), "int"), (pa.string(), "str"),
    (pa.bool_(), "bool"), (pa.timestamp("ms"), "datetime"),
    (pa.date32(), "date"), (pa.null(), None),
])
@pytest.mark.parametrize("values", [[], [None]])
def test_export_schema_resolves_empty_and_all_null_results(arrow_type, expected, values):
    chunk = io.BytesIO()
    pq.write_table(pa.table({"value": pa.array(values, type=arrow_type)}), chunk)
    chunk.seek(0)

    def export(query, draft):
        assert query.limit == 1
        assert query.columns[0].query == "some expression"
        assert draft is True
        return SimpleNamespace(wait_for_execution=lambda: None, get_chunks=lambda: iter([chunk]))

    connection = KnowledgeModelConnection.__new__(KnowledgeModelConnection)
    connection._native = SimpleNamespace(_create_data_export=export)
    connection._draft = True
    assert connection._type_of("some expression") == expected
