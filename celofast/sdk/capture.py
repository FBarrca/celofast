"""Lossless, offline captures of effective Knowledge Model definitions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from functools import cached_property
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

FORMAT_VERSION: Literal[1] = 1

# Only collections whose KM semantics are keyed by ID are reordered. Arbitrary
# metadata arrays, parameters, priorities, and unknown collections retain order.
_ROOT_COLLECTIONS = frozenset(
    {
        "records",
        "kpis",
        "filters",
        "variables",
        "activities",
        "actions",
        "anomalies",
        "eventLogs",
        "customObjects",
    }
)
_RECORD_COLLECTIONS = frozenset({"attributes", "newAttributes", "augmentedAttributes"})


class CaptureError(ValueError):
    """A source definition cannot be captured faithfully."""


class Source(BaseModel):
    """Non-secret provenance required to bind a capture to its source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str
    space_id: str
    package_id: str
    key: str
    mode: Literal["draft", "published"]

    @field_validator("tenant_id", "space_id", "package_id", "key")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Source identifiers must not be empty.")
        return value


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _normalize(value: Any, path: tuple[str, ...] = ()) -> Any:
    location = "/" + "/".join(path)
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise CaptureError(f"{location}: definition keys must be strings.")
        return {
            key: _normalize(item, (*path, key)) for key, item in sorted(value.items())
        }
    if isinstance(value, list):
        result = [
            _normalize(item, (*path, str(index))) for index, item in enumerate(value)
        ]
        keyed = (
            len(path) == 1
            and path[0] in _ROOT_COLLECTIONS
            or len(path) == 3
            and path[0] == "records"
            and path[2] in _RECORD_COLLECTIONS
        )
        if keyed:
            ids = [item.get("id") for item in result if isinstance(item, dict)]
            present = [item for item in ids if isinstance(item, str) and item]
            if len(present) != len(set(present)):
                raise CaptureError(f"{location}: duplicate source IDs.")
            # Missing IDs and null entries survive exactly; structural paths
            # remain meaningful by retaining their original order.
            if len(present) == len(result):
                result.sort(key=lambda item: item["id"])
        return result
    if value is None or type(value) in (str, bool, int, float):
        return value
    raise CaptureError(
        f"{location}: unsupported definition value {type(value).__name__}."
    )


class Capture(BaseModel):
    """Immutable canonical source content; no client or live object is retained."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    format_version: Literal[1] = FORMAT_VERSION
    source: Source
    definition_json: str

    @model_validator(mode="before")
    @classmethod
    def decode_sidecar(cls, value: Any) -> Any:
        if isinstance(value, dict) and "definition" in value:
            if "definition_json" in value:
                raise ValueError("Capture must contain one canonical definition.")
            value = dict(value)
            value["definition_json"] = json.dumps(
                value.pop("definition"), ensure_ascii=False, allow_nan=False
            )
        return value

    @field_validator("definition_json")
    @classmethod
    def canonical_definition(cls, value: str) -> str:
        try:
            payload = json.loads(value)
            if not isinstance(payload, dict):
                raise CaptureError("KM definitions must be a JSON object.")
            return json.dumps(
                _normalize(payload),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid KM definition: {exc}") from exc

    @model_validator(mode="after")
    def matching_provenance(self) -> Capture:
        layer = self.to_dict()
        if layer.get("tenantId", self.source.tenant_id) != self.source.tenant_id:
            raise ValueError("KM tenantId does not match capture provenance.")
        metadata = layer.get("metadata")
        if (
            isinstance(metadata, dict)
            and metadata.get("key", self.source.key) != self.source.key
        ):
            raise ValueError("KM metadata.key does not match capture provenance.")
        return self

    @classmethod
    def create(cls, source: Source, definition: Mapping[str, Any]) -> Capture:
        """Detach from source state, preserving unknown fields and exact strings."""
        normalized = _normalize(definition)
        try:
            encoded = json.dumps(normalized, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise CaptureError(f"Invalid KM definition: {exc}") from exc
        tenant_id = normalized.get("tenantId")
        if tenant_id is not None and tenant_id != source.tenant_id:
            raise CaptureError("KM tenantId does not match capture provenance.")
        metadata = normalized.get("metadata")
        if isinstance(metadata, dict) and metadata.get("key", source.key) != source.key:
            raise CaptureError("KM metadata.key does not match capture provenance.")
        return cls(source=source, definition_json=encoded)

    @cached_property
    def fingerprint(self) -> str:
        """Definition fingerprint, independent of retrieval time and object order."""
        return hashlib.sha256(self.definition_json.encode("utf-8")).hexdigest()

    @cached_property
    def definition(self) -> Mapping[str, Any]:
        """Deeply immutable definition metadata, including unknown fields."""
        return _freeze(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        """Return a detached JSON-compatible copy for execution or serialization."""
        return json.loads(self.definition_json)

    def to_json(self) -> str:
        """Readable, versioned sidecar with ordinary JSON definition fields."""
        return (
            json.dumps(
                {
                    "format_version": self.format_version,
                    "source": self.source.model_dump(),
                    "definition": self.to_dict(),
                },
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )


def retrieve(
    native: Any, *, space_id: str, package_id: str, mode: Literal["draft", "published"]
) -> Capture:
    """Read one final-layer response through the authenticated PyCelonis client.

    The endpoint and options mirror PyCelonis 2.15.1's get_content. Reading the
    raw JSON avoids lossy transport models and explicitly selects lifecycle.
    No second definition request is used to assemble the capture.
    """
    from urllib.parse import quote

    if mode not in ("draft", "published"):
        raise CaptureError("mode must be 'draft' or 'published'.")
    if not isinstance(native.root_with_key, str) or not native.root_with_key:
        raise CaptureError("KM has no root_with_key for effective-content retrieval.")
    response = native.client.request(
        method="POST",
        url=f"/semantic-layer/api/layer/{quote(native.root_with_key, safe='')}/final",
        params={"isDraft": mode == "draft"},
        json={
            "withVariableReplacement": False,
            "withAutogeneratedDataModelData": True,
            "withDefaultValues": True,
            "validatePql": True,
            "withUnknownVariablesValidation": True,
        },
        parse_json=True,
    )
    layer = response.get("layer") if isinstance(response, dict) else None
    if not isinstance(layer, dict):
        raise CaptureError("Effective KM response has no definition layer.")
    tenant_id = layer.get("tenantId")
    if not isinstance(tenant_id, str) or not tenant_id:
        raise CaptureError(
            "Effective KM response has no tenantId for source validation."
        )
    source = Source(
        tenant_id=tenant_id,
        space_id=space_id,
        package_id=package_id,
        key=native.key,
        mode=mode,
    )
    return Capture.create(source, layer)
