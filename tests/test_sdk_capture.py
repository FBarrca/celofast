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
        input_variables={"months": {"defaultValue": "3", "dataType": "TEXT"}},
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
        if kwargs["method"] == "GET":
            revision = kwargs.get("params", {}).get("draftId", "draft")
            return {
                "id": "node",
                "key": "inventory-km",
                "draftId": revision,
                "workingDraftId": "draft",
                "activatedDraftId": "published",
                "inputVariableDefinitions": [
                    {
                        "key": "months",
                        "defaultValue": revision,
                        "futureMetadata": [2, 1],
                    }
                ],
            }
        return {
            "layer": {
                "tenantId": "tenant",
                "nodeEntityId": "node",
                "futureCategory": [{"id": "future", "new": 42}],
            },
            "unrelatedEnvelope": "not captured",
        }

    native = SimpleNamespace(
        root_with_key="package.inventory-km",
        key="inventory-km",
        client=SimpleNamespace(request=request),
    )
    capture = retrieve(native, space_id="space", package_id="package", mode=mode)
    assert len(calls) == (2 if mode == "draft" else 3)
    assert capture.input_variables["months"]["defaultValue"] == mode
    assert capture.input_variables["months"]["futureMetadata"] == [2, 1]
    assert calls[0]["params"] == {"isDraft": mode == "draft"}
    assert calls[0]["json"]["withVariableReplacement"] is False
    assert "type_" not in calls[0]
    assert capture.definition["futureCategory"] == [{"id": "future", "new": 42}]
    assert "unrelatedEnvelope" not in capture.definition


def test_missing_published_input_revision_does_not_fall_back():
    def request(**kwargs):
        if kwargs["method"] == "POST":
            return {"layer": {"tenantId": "tenant", "nodeEntityId": "node"}}
        return {"workingDraftId": "draft", "activatedDraftId": None}

    native = SimpleNamespace(
        root_with_key="package.inventory-km",
        key="inventory-km",
        client=SimpleNamespace(request=request),
    )
    with pytest.raises(CaptureError, match="no published revision"):
        retrieve(native, space_id="space", package_id="package", mode="published")
