"""Count related source objects once when their join uses a shared child table."""

import json

import pytest

from celofast.sdk import Capture
from celofast.sdk.expressions import Expressions
from celofast.sdk.generate import generate
from celofast.sdk.validation import validate

from objects_fixture import SOURCE, attribute, load


COUNT = 'PU_COUNT("Target", "Source"."ID")'
BOUND = 'PU_COUNT_DISTINCT("Target", BIND("Bridge", "Source"."ID"))'


def capture():
    return Capture.create(SOURCE, {"records": [{
        "id": "TARGET", "pql": "Target", "attributes": [
            attribute("ID", '"Target"."ID"'),
            attribute("NumSources", COUNT, "INTEGER"),
            attribute("HasSources", 'CASE WHEN "Target"."NumSources" > 0 THEN \'X\' END'),
        ],
    }], "kpis": [{"id": "CountSources", "pql": COUNT}]}, tables={
        "Target": {"primary_key": ["ID"], "columns": {"ID": "STRING"}},
        "Source": {"primary_key": ["ID"], "columns": {"ID": "STRING", "Name": "STRING"}},
        "Bridge": {"primary_key": ["ID"], "columns": {"ID": "STRING", "Target_ID": "STRING", "Source_ID": "STRING"}},
    }, joins=[
        {"one": "Target", "many": "Bridge", "columns": [["ID", "Target_ID"]]},
        {"one": "Source", "many": "Bridge", "columns": [["ID", "Source_ID"]]},
    ])


def test_key_count_and_dependent_attributes_are_repaired_without_input_variables(tmp_path):
    cap = capture()
    before = cap.to_json()
    probes = []

    def execute(expressions, limit):
        probes.append(expressions)
        assert expressions[1] == f"({BOUND}\n)"
        assert BOUND in expressions[2] and '"NumSources"' not in expressions[2]
        return [("T1", 2, "X"), ("T2", 0, None)]

    assert validate(cap, execute) == {}
    for name, content in generate(cap).items():
        (tmp_path / name).write_bytes(content)
    sdk = load(tmp_path, "count_bridge_sdk")
    assert sdk.Target.fields.num_sources.expression == BOUND
    assert probes[0][2] == f"({sdk.Target.fields.has_sources.expression}\n)"
    assert Expressions(cap).resolve("KPI(CountSources)") == f"({BOUND}\n)"
    assert cap.to_json() == before


@pytest.mark.parametrize("expression", [
    'PU_COUNT("Target", "Source"."Name")',
    'PU_COUNT("Target", "Source"."ID", "Source"."Name" = \'A\')',
    'PU_COUNT_DISTINCT("Target", "Source"."ID")',
    'PU_COUNT("Source", "Bridge"."ID")',
    '\'PU_COUNT("Target", "Source"."ID")\' /* PU_COUNT("Target", "Source"."ID") */',
])
def test_other_counts_and_literal_text_are_preserved(expression):
    assert Expressions(capture()).resolve(expression) == expression


@pytest.mark.parametrize("change", ["ambiguous", "parallel_fk", "direct", "reverse", "multi_hop", "composite", "no_key"])
def test_repair_requires_one_unambiguous_bridge_and_one_source_key(change):
    payload = json.loads(capture().to_json())
    if change == "ambiguous":
        payload["joins"].extend([
            {"one": "Target", "many": "OtherBridge", "columns": [["ID", "Target_ID"]]},
            {"one": "Source", "many": "OtherBridge", "columns": [["ID", "Source_ID"]]},
        ])
    elif change == "parallel_fk":
        payload["joins"].append({"one": "Source", "many": "Bridge", "columns": [["ID", "OtherSource_ID"]]})
    elif change == "direct":
        payload["joins"].append({"one": "Target", "many": "Source", "columns": [["ID", "Target_ID"]]})
    elif change == "reverse":
        payload["joins"].append({"one": "Source", "many": "Target", "columns": [["ID", "Source_ID"]]})
    elif change == "multi_hop":
        payload["joins"].extend([
            {"one": "Target", "many": "Middle", "columns": [["ID", "Target_ID"]]},
            {"one": "Middle", "many": "Source", "columns": [["ID", "Middle_ID"]]},
        ])
    else:
        payload["tables"]["Source"]["primary_key"] = ["ID", "Name"] if change == "composite" else []
    assert Expressions(Capture.model_validate(payload)).resolve(COUNT) == COUNT
