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


def test_lossless_capture_is_detached_and_deeply_immutable():
    pql = '\n"Plant"."Number" || \' - \' || "Plant"."Name"\\\n'
    payload = {
        "unknown": {"explicitNull": None, "sequence": [2, 1]},
        "records": [{"id": "Plant", "attributes": [{"id": "Name", "pql": pql}]}],
    }
    capture = Capture.create(source(), payload)
    payload["unknown"]["sequence"].append(3)
    assert capture.to_dict()["unknown"] == {"explicitNull": None, "sequence": [2, 1]}
    assert capture.definition["records"][0]["attributes"][0]["pql"] == pql
    with pytest.raises(TypeError):
        capture.definition["unknown"]["explicitNull"] = 1
    with pytest.raises(AttributeError):
        capture.definition["unknown"]["sequence"].append(4)
    detached = capture.to_dict()
    detached["unknown"].clear()
    assert "explicitNull" in capture.definition["unknown"]


def test_fingerprint_ignores_known_object_order_but_preserves_unknown_order():
    first = Capture.create(
        source(), {"records": [{"id": "b"}, {"id": "a"}], "steps": [2, 1]}
    )
    second = Capture.create(
        source(), {"steps": [2, 1], "records": [{"id": "a"}, {"id": "b"}]}
    )
    assert first.fingerprint == second.fingerprint
    changed = Capture.create(source(), {**first.to_dict(), "steps": [1, 2]})
    assert changed.fingerprint != first.fingerprint
    assert Capture.model_validate_json(first.model_dump_json()) == first
    assert Capture.model_validate_json(first.to_json()) == first
    assert '"definition_json"' not in first.to_json()


@pytest.mark.parametrize(
    "payload",
    [
        {"records": [{"id": "duplicate"}, {"id": "duplicate"}]},
        {"unknown": object()},
        {"unknown": float("nan")},
        {"tenantId": "other"},
        {"metadata": {"key": "other"}},
    ],
)
def test_invalid_content_is_rejected(payload):
    with pytest.raises(CaptureError):
        Capture.create(source(), payload)


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
    assert capture.input_variables["months"]["futureMetadata"] == (2, 1)
    assert calls[0]["params"] == {"isDraft": mode == "draft"}
    assert calls[0]["json"]["withVariableReplacement"] is False
    assert "type_" not in calls[0]
    assert capture.to_dict()["futureCategory"] == [{"id": "future", "new": 42}]
    assert "unrelatedEnvelope" not in capture.definition


def test_input_defaults_are_detached_and_part_of_integrity():
    from celofast.sdk.loading import capture_digest

    inputs = {
        "months": {"defaultValue": "3", "dataType": "TEXT"},
        "optional": {"defaultValue": None},
    }
    old = Capture.create(source(), {"variables": []}, input_variables=inputs)
    inputs["months"]["defaultValue"] = "6"
    new = Capture.create(source(), old.to_dict(), input_variables=inputs)
    assert old.input_variables["months"]["defaultValue"] == "3"
    assert old.input_variables["optional"]["defaultValue"] is None
    with pytest.raises(TypeError):
        old.input_variables["months"]["defaultValue"] = "6"
    assert old.definition == new.definition
    assert old.fingerprint != new.fingerprint
    assert capture_digest(old) != capture_digest(new)
    assert Capture.model_validate_json(old.to_json()) == old
    legacy = Capture.create(source(), {})
    assert legacy.input_variables is None
    assert "input_variables" not in legacy.to_json()


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
