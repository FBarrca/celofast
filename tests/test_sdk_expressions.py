"""KM input variables: input-dependent references are inlined with their
placeholders at pull, and every placeholder is bound at query time."""

from datetime import datetime

import pytest

from celofast.exceptions import UnresolvedVariableError
from celofast.sdk import Capture
from celofast.sdk.expressions import References, bind_inputs
from celofast.sdk.generate import generate
from celofast.sdk.model import normalize
from celofast.sdk.validation import validate

from objects_fixture import SOURCE, attribute, load


def capture(default="Requested", due=None):
    return Capture(source=SOURCE, definition={"records": [{
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
    }]}, input_variables={"choice": {"dataType": "TEXT", "value": default}}, tables={"o_Line": {"primary_key": ["ID"], "columns": {
            "ID": "STRING", "RequestedDate": "DATE", "ConfirmedDate": "DATE",
        }}})


def bind(expression, value, data_type="TEXT"):
    return bind_inputs(expression, lambda name: value, {"choice": data_type})


def test_generated_fields_keep_placeholders_and_pull_tests_them_with_pull_values(tmp_path):
    cap = capture()
    original = cap.model_dump_json()
    probes = []

    def execute(expressions, limit):
        probes.append(expressions)
        assert all("${choice}" not in expression for expression in expressions)
        return [("L1", datetime(2024, 1, 31), "LATE", 1)]

    assert validate(cap, execute).validation == {}
    assert len(probes) == 1
    for name, content in generate(cap).items():
        (tmp_path / name).write_bytes(content)
    sdk = load(tmp_path, "resolved_input_sdk")
    due = sdk.Line.fields.due_date
    # A direct placeholder is kept and bound per read (here, for the test run).
    assert due.expression.startswith("CASE WHEN ${choice} LIKE 'Requested'")
    assert probes[0][1] == f"({bind(due.expression, 'Requested')}\n)"
    assert "'Requested' LIKE 'Requested'" in probes[0][1]
    # References to input-dependent attributes are inlined, placeholders and
    # all: Celonis would bind a referenced attribute's inputs raw.
    late = sdk.Line.fields.is_delivered_late
    classification = sdk.Line.fields.classification.expression
    assert classification == f"CASE WHEN ({due.expression}\n) < TODAY() THEN 'LATE' ELSE 'ON_TIME' END"
    assert (late.value_type, late.expression) == (
        "int", f"CASE WHEN ({classification}\n) = 'LATE' THEN 1 ELSE 0 END"
    )
    assert probes[0][3] == f"({bind(late.expression, 'Requested')}\n)"
    assert sdk.km.variables == {"choice": "TEXT"}
    assert cap.model_dump_json() == original  # Resolving never edits the captured source.


def test_inputs_without_a_value_still_load_and_are_not_test_run():
    fields = {f.attribute_id: f for f in normalize(capture(None)).objects[0].fields}
    # DueDate, and the attributes that reach it through references.
    for name in ("DueDate", "Classification", "IsDeliveredLate"):
        assert "${choice}" in fields[name].expression

    def execute(expressions, limit):
        raise AssertionError("nothing is test-run without input values")

    assert validate(capture(None), execute).validation == {}


def test_attributes_without_inputs_stay_references():
    cap = capture(due='"o_Line"."RequestedDate"')
    fields = {f.attribute_id: f for f in normalize(cap).objects[0].fields}
    assert fields["IsDeliveredLate"].expression == (
        "CASE WHEN \"o_Line\".\"Classification\" = 'LATE' THEN 1 ELSE 0 END"
    )


def test_references_by_record_id_are_inlined():
    inlined = References(capture()).resolve('"O_LINE"."DueDate"')
    assert inlined.startswith("(CASE WHEN ${choice} LIKE 'Requested'")


def test_dependency_cycles_are_reported_without_recursing_forever():
    result = normalize(capture(due='"o_Line"."Classification"'))
    assert any("cyclic calculated attribute" in d for d in result.diagnostics)


def test_physical_columns_never_expand_to_calculated_definitions():
    cap = capture()
    layer = cap.definition
    layer["records"][0]["attributes"].append(attribute("RequestedDate", "${choice}"))
    changed = Capture(source=SOURCE, definition=layer, input_variables=cap.input_variables, tables=cap.tables)
    assert References(changed).resolve('"o_Line"."RequestedDate"') == '"o_Line"."RequestedDate"'


def kpi_capture():
    return Capture(source=SOURCE, definition={"records": [{
        "id": "O_LINE", "pql": "o_Line", "attributes": [
            attribute("ID", '"o_Line"."ID"'),
            attribute("ActualPurchaseLeadTime", "CASE WHEN ${choice} = 'Average' THEN 1 ELSE 2 END", "FLOAT"),
        ],
    }], "kpis": [
        {"id": "IsLegacy", "pql": 'KPI("LeadTime")', "parameters": []},
        {"id": "LeadTime", "pql": '"o_Line"."ActualPurchaseLeadTime"'},
        {"id": "Constant", "pql": "1.0"},
        {"id": "Parameterized", "pql": "${choice}", "parameters": [{"id": "ARG"}]},
    ]}, input_variables={"choice": {"dataType": "TEXT", "value": "Average"}},
        tables={"o_Line": {"primary_key": ["ID"], "columns": {"ID": "STRING"}}})


LEAD_TIME = "(CASE WHEN ${choice} = 'Average' THEN 1 ELSE 2 END\n)"


@pytest.mark.parametrize(("expression", "expected"), [
    ("KPI(LeadTime)", f"({LEAD_TIME}\n)"),
    ('kpi ( "leadtime" )', f"({LEAD_TIME}\n)"),
    ("CASE WHEN KPI (\n IsLegacy\n) > 0 THEN 10.0 ELSE 0.0 END",
     f"CASE WHEN (({LEAD_TIME}\n)\n) > 0 THEN 10.0 ELSE 0.0 END"),
])
def test_input_dependent_kpis_are_inlined(expression, expected):
    assert References(kpi_capture()).resolve(expression) == expected


def test_kpi_text_and_other_kpis_are_preserved():
    references = References(kpi_capture())
    expression = "'KPI(LeadTime)' /* KPI(LeadTime) */ -- KPI(LeadTime)\n \"KPI(LeadTime)\""
    assert references.resolve(expression) == expression
    for expression in ("KPI(Constant)", "KPI(Unknown)", "KPI(Parameterized)", "KPI(Parameterized, 3)"):
        assert references.resolve(expression) == expression


def test_cycles_through_kpis_and_attributes_are_reported():
    cap = kpi_capture()
    cap.definition["records"][0]["attributes"][1]["pql"] = "KPI(IsLegacy)"
    assert any("cyclic calculated attribute or KPI" in d for d in normalize(cap).diagnostics)


def test_quoted_placeholders_and_text_values_are_escaped_once():
    assert bind("${choice} = '${choice}'", "O'Brien\\x") == "'O\\'Brien\\\\x' = 'O\\'Brien\\\\x'"
    assert bind("'-- ${choice}'", "O'Brien\\x") == "'-- O\\'Brien\\\\x'"


def test_comments_and_column_names_are_not_variable_substitutions():
    expression = '"o_Line"."${choice}" /* ${choice} */ -- ${choice}\n + ${choice}'
    assert bind(expression, "Requested") == (
        '"o_Line"."${choice}" /* ${choice} */ -- ${choice}\n + \'Requested\''
    )


@pytest.mark.parametrize("value", ["3", "-1.5", "2e3"])
def test_numeric_values_stay_numeric_even_in_text_inputs(value):
    assert bind("${choice} * 2", value) == f"{value} * 2"
    assert bind("'${choice}'", value) == f"'{value}'"


@pytest.mark.parametrize(("data_type", "value", "expected"), [
    ("NUMBER", "12", "12"),
    ("BOOLEAN", "true", "1"),
    ("BOOLEAN", "False", "0"),
    ("PQL", '"o_Line"."ID"', '"o_Line"."ID"'),
    (None, "raw", "raw"),
])
def test_values_are_formatted_by_their_data_type(data_type, value, expected):
    assert bind("${choice}", value, data_type) == expected


def test_a_placeholder_without_a_value_is_an_error():
    with pytest.raises(UnresolvedVariableError, match=r"\$\{choice\}"):
        bind("${choice}", None)


@pytest.mark.parametrize("expression", [
    'PU_COUNT("Target", "Source"."ID")',  # Across a shared child table: not repaired.
    'KPI(Unknown)',
])
def test_km_pql_is_never_repaired(expression):
    # Celonis rejects PQL that fails at pull; celofast does not rewrite it.
    cap = capture(due=expression)
    due = next(f for f in normalize(cap).objects[0].fields if f.attribute_id == "DueDate")
    assert due.expression == expression
