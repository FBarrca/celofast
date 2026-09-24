"""A pull must not rely on the server to quote nested KM input defaults."""

import json

import pytest

from celofast.sdk import Capture
from celofast.sdk.expressions import Expressions
from celofast.sdk.generate import generate
from celofast.sdk.mapping import normalize
from celofast.sdk.validation import validate

from objects_fixture import SOURCE, attribute, load


def capture(default="Requested", due=None):
    return Capture.create(SOURCE, {"records": [{
        "id": "O_LINE", "pql": "o_Line",
        "attributes": [
            attribute("ID", '"o_Line"."ID"'),
            attribute("DueDate", due or (
                "CASE WHEN ${choice} LIKE 'Requested' THEN "
                '"o_Line"."RequestedDate" ELSE "o_Line"."ConfirmedDate" END'
            ), "DATE"),
            attribute("Classification", 'CASE WHEN "o_Line"."DueDate" < TODAY() THEN \'LATE\' ELSE \'ON_TIME\' END'),
            attribute("IsDeliveredLate", 'CASE WHEN "o_Line"."Classification" = \'LATE\' THEN 1 ELSE 0 END', "INTEGER"),
        ],
    }]}, input_variables={"choice": {"dataType": "TEXT", "defaultValue": default}},
        tables={"o_Line": {"primary_key": ["ID"], "columns": {
            "ID": "STRING", "RequestedDate": "DATE", "ConfirmedDate": "DATE",
        }}})


def test_pull_validation_and_generated_reads_share_resolved_pql(tmp_path):
    cap = capture()
    original = cap.to_json()
    probes = []

    def execute(expressions, limit):
        probes.append(expressions)
        assert all("${choice}" not in expression for expression in expressions)
        assert all('"DueDate"' not in expression for expression in expressions)
        assert "'Requested' LIKE 'Requested'" in expressions[-1]
        return [("L1", "LATE", 1)]

    assert validate(cap, execute) == {}
    assert len(probes) == 1
    for name, content in generate(cap).items():
        (tmp_path / name).write_bytes(content)
    sdk = load(tmp_path, "resolved_input_sdk")
    field = sdk.Line.fields.is_delivered_late
    assert field.value_type == "int"
    assert probes[0][-1] == f"({field.expression}\n)"
    assert "'Requested' LIKE 'Requested'" in field.expression
    assert sdk.km.variables == ()
    assert cap.to_json() == original  # Resolving never edits the captured source.


def test_quoted_placeholders_and_text_values_are_escaped_once():
    resolver = Expressions(capture("O'Brien\\x"))
    resolved = resolver.resolve("${choice} = '${choice}'")
    assert resolved == "'O\\'Brien\\\\x' = 'O\\'Brien\\\\x'"
    assert resolver.resolve("'-- ${choice}'") == "'-- O\\'Brien\\\\x'"


def test_comments_and_column_names_are_not_variable_substitutions():
    resolver = Expressions(capture())
    expression = '"o_Line"."${choice}" /* ${choice} */ -- ${choice}\n + ${choice}'
    assert resolver.resolve(expression) == (
        '"o_Line"."${choice}" /* ${choice} */ -- ${choice}\n + \'Requested\''
    )
    assert resolver.resolve("'\"o_Line\".\"DueDate\"'") == "'\"o_Line\".\"DueDate\"'"


@pytest.mark.parametrize("default", ["3", "-1.5", "2e3"])
def test_numeric_defaults_stay_numeric_even_in_text_inputs(default):
    resolver = Expressions(capture(default))
    assert resolver.resolve("${choice} * 2") == f"{default} * 2"
    assert resolver.resolve("'${choice}'") == f"'{default}'"


def test_missing_defaults_report_the_dependency_instead_of_a_server_error():
    result = normalize(capture(None))
    assert [field.attribute_id for field in result.objects[0].fields] == ["ID"]
    assert any("IsDeliveredLate: calculated dependency needs KM input values" in d
               for d in result.diagnostics)


def test_explicit_input_fields_keep_runtime_bindings():
    result = normalize(capture(), {"objects": {"O_LINE": {"include-fields": ["IsDeliveredLate"]}}})
    late = next(field for field in result.objects[0].fields if field.attribute_id == "IsDeliveredLate")
    assert "${choice}" in late.expression
    assert '"DueDate"' not in late.expression


def test_dependency_cycles_are_reported_without_recursing_forever():
    result = normalize(capture(due='"o_Line"."Classification"'))
    assert any("cyclic calculated attribute" in d for d in result.diagnostics)


def test_physical_columns_never_expand_to_calculated_definitions():
    cap = capture()
    layer = cap.to_dict()
    layer["records"][0]["attributes"].append(attribute("RequestedDate", "${choice}"))
    changed = Capture.create(SOURCE, layer, input_variables=cap.input_variables,
                             tables=json.loads(cap.tables_json))
    assert Expressions(changed).resolve('"o_Line"."RequestedDate"') == '"o_Line"."RequestedDate"'


def kpi_capture():
    return Capture.create(SOURCE, {"records": [{
        "id": "O_LINE", "pql": "o_Line", "attributes": [
            attribute("ID", '"o_Line"."ID"'),
            attribute("ActualPurchaseLeadTime", "CASE WHEN ${choice} = 'Average' THEN 1 ELSE 2 END", "FLOAT"),
            attribute("LegacyStockValue", "CASE WHEN KPI (\n IsLegacy\n) > 0 THEN 10.0 ELSE 0.0 END", "FLOAT"),
        ],
    }], "kpis": [
        {"id": "IsLegacy", "pql": 'KPI("LeadTime")', "parameters": []},
        {"id": "LeadTime", "pql": '"o_Line"."ActualPurchaseLeadTime"'},
        {"id": "Constant", "pql": "1.0"},
        {"id": "Parameterized", "pql": "${choice}", "parameters": [{"id": "ARG"}]},
    ]}, input_variables={"choice": {"dataType": "TEXT", "defaultValue": "Average"}},
        tables={"o_Line": {"primary_key": ["ID"], "columns": {"ID": "STRING"}}})


def test_nested_kpi_inputs_are_bound_for_validation_and_generated_reads(tmp_path):
    cap = kpi_capture()
    original = cap.to_json()
    probes = []

    def execute(expressions, limit):
        probes.append(expressions)
        assert "'Average' = 'Average'" in expressions[-1]
        assert "KPI" not in expressions[-1]
        assert '"ActualPurchaseLeadTime"' not in expressions[-1]
        assert "${" not in expressions[-1]
        return [("L1", 10.0)]

    assert validate(cap, execute) == {}
    for name, content in generate(cap).items():
        (tmp_path / name).write_bytes(content)
    sdk = load(tmp_path, "kpi_inputs_sdk")
    assert probes[0][-1] == f"({sdk.Line.fields.legacy_stock_value.expression}\n)"
    assert cap.to_json() == original


@pytest.mark.parametrize("expression", ['KPI(LeadTime)', 'kpi ( "leadtime" )'])
def test_quoted_and_unquoted_kpi_names_resolve_case_insensitively(expression):
    assert "'Average' = 'Average'" in Expressions(kpi_capture()).resolve(expression)


def test_kpi_text_and_unaffected_calls_are_preserved():
    resolver = Expressions(kpi_capture())
    expression = '\'KPI(LeadTime)\' /* KPI(LeadTime) */ -- KPI(LeadTime)\n "KPI(LeadTime)"'
    assert resolver.resolve(expression) == expression
    for expression in ('KPI(Constant)', 'KPI(Unknown)', 'KPI(Parameterized)', 'KPI(Parameterized, 3)'):
        assert resolver.resolve(expression) == expression


def test_kpi_dependencies_keep_explicit_runtime_inputs_and_report_missing_defaults():
    cap = kpi_capture()
    mapping = {"objects": {"O_LINE": {"include-fields": ["LegacyStockValue"]}}}
    field = normalize(cap, mapping).objects[0].fields[-1]
    assert "${choice}" in field.expression and "KPI" not in field.expression
    missing = Capture.create(SOURCE, cap.to_dict(), input_variables={"choice": {"dataType": "TEXT"}},
                             tables=json.loads(cap.tables_json))
    assert any("LegacyStockValue: calculated dependency needs KM input values" in d
               for d in normalize(missing).diagnostics)


def test_cycles_through_kpis_and_attributes_are_reported():
    cap = kpi_capture()
    layer = cap.to_dict()
    layer["records"][0]["attributes"][1]["pql"] = "KPI(IsLegacy)"
    cap = Capture.create(SOURCE, layer, input_variables=cap.input_variables,
                         tables=json.loads(cap.tables_json))
    assert any("cyclic calculated attribute or KPI" in d for d in normalize(cap).diagnostics)
