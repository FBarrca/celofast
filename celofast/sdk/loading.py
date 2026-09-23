"""Compatibility checks for generated package imports."""

from __future__ import annotations

# 7: self-contained Python packages (no capture.json or schema.json sidecars).
# 6: object SDK (value classes, definitions, links); the query API was removed.
RUNTIME_API_VERSION = 7


class SDKCompatibilityError(ImportError):
    """Generated declarations cannot safely use this runtime."""


def require_runtime(version: int) -> None:
    """Fail at import when a package was generated for another runtime."""
    if version != RUNTIME_API_VERSION:
        raise SDKCompatibilityError(
            f"Generated KM package targets runtime API {version}; this Celofast "
            f"provides {RUNTIME_API_VERSION}. Upgrade Celofast or rerun celofast km pull."
        )


def load_capture(*_: object, **__: object) -> None:
    """Called by packages from before runtime API 7; always incompatible."""
    raise SDKCompatibilityError(
        "Generated KM package uses capture.json from an older Celofast. "
        "Rerun celofast km pull and restart Python."
    )
