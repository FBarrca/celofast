from types import SimpleNamespace

import pytest

from celofast.sdk import Capture, CaptureError, Source
from celofast.sdk.capture import retrieve


def source(mode="draft"):
    return Source(
        tenant_id="tenant",
        space_id="space",
        package_id="package",
        key="inventory-km",
        mode=mode,
    )


def test_capture_round_trips_through_json_exactly():
    pql = '\n"Plant"."Number" || \' - \' || "Plant"."Name"\\\n'
    capture = Capture(
        source=source(),
        definition={
            "unknown": {"explicitNull": None, "sequence": [2, 1]},
            "records": [{"id": "Plant", "attributes": [{"id": "Z", "pql": pql}, {"id": "A", "pql": "2"}]}],
        },
        input_variables={"months": {"dataType": "TEXT", "value": "3"}},
        joins=[{"one": "a", "many": "b", "columns": [["ID", "A_ID"]]}],
        tables={"a": {"primary_key": ["ID"], "columns": {"ID": "STRING"}}},
        validation={"Plant": {"Z": "fails in Celonis: boom"}},
        types={"UPPER(1)": "str"},
    )
    again = Capture.model_validate_json(capture.model_dump_json())
    assert again == capture
    assert again.definition["records"][0]["attributes"][0]["pql"] == pql
    assert [a["id"] for a in again.definition["records"][0]["attributes"]] == ["Z", "A"]
    minimal = Capture(source=source(), definition={})
    assert (minimal.input_variables, minimal.joins, minimal.tables) == (None, None, None)
    assert (minimal.validation, minimal.types) == ({}, {})


def test_source_identifiers_must_not_be_empty():
    with pytest.raises(ValueError, match="must not be empty"):
        Source(tenant_id=" ", space_id="s", package_id="p", key="k", mode="draft")


@pytest.mark.parametrize("mode", ["draft", "published"])
def test_retrieval_preserves_unknown_fields_and_explicit_lifecycle(mode):
    calls = []

    def request(**kwargs):
        calls.append(kwargs)
        return {
            "layer": {"tenantId": "tenant", "futureCategory": [{"id": "future", "new": 42}]},
            "unrelatedEnvelope": "not captured",
        }

    native = SimpleNamespace(
        root_with_key="package.inventory-km",
        key="inventory-km",
        client=SimpleNamespace(request=request),
        get_variables=lambda: [
            SimpleNamespace(key="months", data_type=SimpleNamespace(value="NUMBER"), value_or_default="12"),
            SimpleNamespace(key="plant", data_type="TEXT", value_or_default=None),
        ],
    )
    capture = retrieve(native, space_id="space", package_id="package", mode=mode)
    assert len(calls) == 1
    assert capture.input_variables == {
        "months": {"dataType": "NUMBER", "value": "12"},
        "plant": {"dataType": "TEXT", "value": None},
    }
    assert calls[0]["params"] == {"isDraft": mode == "draft"}
    assert calls[0]["json"]["withVariableReplacement"] is False
    assert capture.definition["futureCategory"] == [{"id": "future", "new": 42}]
    assert "unrelatedEnvelope" not in capture.definition
