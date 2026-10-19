"""Reusable authenticated Celonis client factory."""

from __future__ import annotations

import functools
import os

from dotenv import find_dotenv, load_dotenv

from pycelonis import get_celonis as pycelonis_get_celonis
from pycelonis import oauth2
from pycelonis.celonis import Celonis
from pycelonis_core.client import KeyType


@functools.cache
def get_celonis(base_url: str | None = None) -> Celonis:
    """Return a cached OAuth-authenticated PyCelonis client.

    Args:
        base_url: Optional Celonis tenant URL.  When omitted, the value of
            ``CELONIS_URL`` is used after trimming a trailing slash.

    Returns:
        A cached :class:`pycelonis.Celonis` configured with bearer OAuth,
        ``user_agent="celofast"``, SSL verification, and the package's
        compatibility settings.  Calls with the same ``base_url`` reuse the
        same client instance.

    When neither ``OAUTH_CLIENT_ID`` nor ``OAUTH_CLIENT_SECRET`` is set
    (``OAUTH_SCOPES`` alone is ignored), PyCelonis' own auto-detection is used, which
    works inside the Machine Learning Workbench (MLWB).

    Raises:
        RuntimeError: If OAuth is only partially configured, or configured
            without ``base_url``/``CELONIS_URL``.

    Notes:
        CeloFast does not read Space, Package, KM, or View identifiers from
        environment variables.  Pass those IDs/keys explicitly to
        :class:`celofast.CeloFast`.
        Authentication and any PyCelonis API failures are otherwise allowed
        to propagate with their native exception types.
    """

    load_dotenv(find_dotenv(usecwd=True))
    resolved_base_url = (base_url or os.environ.get("CELONIS_URL", "")).rstrip("/")

    oauth_values = {
        "OAUTH_CLIENT_ID": os.environ.get("OAUTH_CLIENT_ID", ""),
        "OAUTH_CLIENT_SECRET": os.environ.get("OAUTH_CLIENT_SECRET", ""),
        "OAUTH_SCOPES": os.environ.get("OAUTH_SCOPES", ""),
    }

    if not (oauth_values["OAUTH_CLIENT_ID"] or oauth_values["OAUTH_CLIENT_SECRET"]):
        # No OAuth configured: let PyCelonis auto-detect its own credentials
        # (e.g. inside the Machine Learning Workbench, which injects them).
        kwargs = {"base_url": resolved_base_url} if resolved_base_url else {}
        return pycelonis_get_celonis(
            **kwargs,
            user_agent="celofast",
            check_if_outdated=False,
            permissions=False,
        )

    if not resolved_base_url:
        raise RuntimeError("CELONIS_URL must be provided to use the PyCelonis client.")

    missing = [name for name, value in oauth_values.items() if not value]
    if missing:
        raise RuntimeError(
            f"{', '.join(missing)} must be provided to use the PyCelonis client."
        )

    return pycelonis_get_celonis(
        base_url=resolved_base_url,
        api_token=oauth2(
            oauth_values["OAUTH_CLIENT_ID"],
            oauth_values["OAUTH_CLIENT_SECRET"],
            oauth_values["OAUTH_SCOPES"],
        ),
        key_type=KeyType.BEARER,
        user_agent="celofast",
        verify_ssl=True,
        check_if_outdated=False,
        permissions=False,
    )
