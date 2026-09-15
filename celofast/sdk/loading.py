"""Compatibility and integrity checks for generated package imports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from celofast.sdk.capture import Capture

RUNTIME_API_VERSION = 2


class SDKCompatibilityError(ImportError):
    """Generated declarations cannot safely use this runtime or sidecar."""


def capture_digest(capture: Capture) -> str:
    """Hash both provenance and definitions to bind declarations to their data."""
    exclude = (
        {"input_variables_json"} if capture.input_variables_json is None else set()
    )
    return hashlib.sha256(
        capture.model_dump_json(exclude=exclude).encode("utf-8")
    ).hexdigest()


def load_capture(path: Path, *, runtime_api: int, digest: str) -> Capture:
    """Load offline and fail clearly for stale code, data, or runtime versions."""
    if runtime_api not in (1, RUNTIME_API_VERSION):
        raise SDKCompatibilityError(
            "Generated KM runtime is incompatible. Upgrade Celofast or rerun celofast km pull."
        )
    try:
        text = path.read_text(encoding="utf-8")
        raw = json.loads(text)
        if not isinstance(raw, dict) or raw.get("format_version") != 1:
            raise SDKCompatibilityError(
                "Generated KM format is incompatible. Upgrade Celofast or rerun celofast km pull."
            )
        capture = Capture.model_validate_json(text)
    except (OSError, ValueError) as exc:
        raise SDKCompatibilityError(
            f"Cannot load captured KM definitions from {path.name}. Rerun celofast km pull."
        ) from exc
    if capture_digest(capture) != digest:
        raise SDKCompatibilityError(
            "Generated KM declarations and definitions differ. Rerun celofast km pull."
        )
    return capture
