"""Compatibility check for generated package imports."""

from __future__ import annotations

# Bump when generated code needs a different runtime; packages then fail at
# import and must be regenerated with celofast km pull.
RUNTIME_API_VERSION = 11


class SDKCompatibilityError(ImportError):
    """Generated declarations cannot safely use this runtime."""


def require_runtime(version: int) -> None:
    """Fail at import when a package was generated for another runtime."""
    if version != RUNTIME_API_VERSION:
        raise SDKCompatibilityError(
            f"Generated KM package targets runtime API {version}; this Celofast "
            f"provides {RUNTIME_API_VERSION}. Upgrade Celofast or rerun celofast km pull."
        )
