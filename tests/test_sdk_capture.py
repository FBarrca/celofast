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
        return {
            "layer": {
                "tenantId": "tenant",
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
    assert len(calls) == 1
    assert calls[0]["params"] == {"isDraft": mode == "draft"}
    assert calls[0]["json"]["withVariableReplacement"] is False
    assert "type_" not in calls[0]
    assert capture.to_dict()["futureCategory"] == [{"id": "future", "new": 42}]
    assert "unrelatedEnvelope" not in capture.definition
