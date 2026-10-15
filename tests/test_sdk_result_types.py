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
from celofast.sdk.model import normalize
from celofast.sdk.validation import resolve_types, validate

from objects_fixture import SOURCE, attribute, load


def capture():
    return Capture(source=SOURCE, definition={"records": [{
        "id": "O_PLANT", "pql": "o_Plant", "identifier": {"pql": '"o_Plant"."ID"'},
        "attributes": [
            attribute("ID", '"o_Plant"."ID"'),
            attribute("Total", '"o_Plant"."Planned" + "o_Plant"."Purchased"', None),
            attribute("Planned", "COALESCE(PU_SUM(\"o_Plant\", \"o_Order\".\"Quantity\", DAYS_BETWEEN(TODAY(), \"o_Order\".\"Due\") < ${months}), 0.0)", None),
        ],
    }]}, input_variables={"months": {"dataType": "NUMBER", "value": "3"}}, tables={"o_Plant": {"primary_key": ["ID"], "columns": {"ID": "STRING"}}})


@pytest.mark.parametrize("expression", [
    'ADD_HOURS("o_Line"."LastGoodsIssueDate", COALESCE("o_Line"."TransitDurationDays" * 24, 0))',
    '"o_Line"."CalculatedDate"',  # A reference absent from the physical column catalog.
])
def test_incorrect_declared_type_is_corrected_before_validation_and_generation(tmp_path, expression):
    original = Capture(source=SOURCE, definition={"records": [{
        "id": "O_LINE", "pql": "o_Line", "attributes": [
            attribute("ID", '"o_Line"."ID"'),
            attribute("ActualDeliveryTimestamp", expression, "STRING"),
        ],
    }]}, tables={"o_Line": {"primary_key": ["ID"], "columns": {"ID": "STRING"}}})

    def describe(pql):
        assert pql == expression
        return "datetime"

    cap = resolve_types(original, describe)
    assert cap.definition == original.definition
    cap = Capture.model_validate_json(cap.model_dump_json())
    assert validate(cap, lambda expressions, limit: [("L1", datetime(2024, 3, 28)), ("L2", None)]).validation == {}
    for name, content in generate(cap).items():
        (tmp_path / name).write_bytes(content)
    sdk = load(tmp_path, "corrected_type_sdk")
    assert sdk.Line.fields.actual_delivery_timestamp.value_type == "datetime"


def test_inputs_without_a_default_keep_declared_types_without_schema_queries():
    original = Capture(source=SOURCE, definition={"records": [{
        "id": "O_LINE", "pql": "o_Line", "attributes": [
            attribute("ID", '"o_Line"."ID"'),
            attribute("Value", "${choice}", "STRING"),
        ],
    }]}, input_variables={"choice": {"dataType": "TEXT"}},
        tables={"o_Line": {"primary_key": ["ID"], "columns": {"ID": "STRING"}}})
    cap = resolve_types(original, lambda expression: pytest.fail("Without a default there is nothing to run"))
    field = normalize(cap).objects[0].fields[1]
    assert (field.value_type, field.expression) == ("str", "${choice}")


def test_input_attributes_are_typed_with_pull_values_but_keep_their_placeholders(tmp_path):
    original = capture()
    described = []

    def describe(expression):
        described.append(expression)
        assert "${months}" not in expression
        return "float"

    cap = resolve_types(original, describe)
    # Planned uses ${months} directly: bound for the run. Total references
    # Planned, so Planned is inlined into it and bound the same way.
    # Types are described concurrently, in no fixed order.
    described.sort(key=lambda expression: expression.endswith('"o_Plant"."Purchased"'), reverse=True)
    assert len(described) == 2 and "< 3)" in described[1]
    assert described[0] == f'({described[1]}\n) + "o_Plant"."Purchased"'
    assert cap.definition == original.definition
    assert original.types == {}
    cap = Capture.model_validate_json(cap.model_dump_json())

    def execute(expressions, limit):
        assert [e[1:-2] for e in expressions[1:]] == described
        return [("P1", 1.25, 1.0), ("P2", None, None)]

    assert validate(cap, execute).validation == {}
    for name, content in generate(cap).items():
        (tmp_path / name).write_bytes(content)
    sdk = load(tmp_path, "result_type_sdk")
    assert sdk.Plant.fields.total.value_type == "float"
    planned = sdk.Plant.fields.planned.expression
    assert "${months}" in planned
    assert sdk.Plant.fields.total.expression == f'({planned}\n) + "o_Plant"."Purchased"'
    assert sdk.km.variables == {"months": "NUMBER"}


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
    (pa.date32(), None), (pa.null(), None),  # Celonis has no date-only type.
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
