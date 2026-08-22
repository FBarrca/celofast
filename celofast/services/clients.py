"""Reusable authenticated Celonis client factories."""

from __future__ import annotations

import functools
import os
from typing import Union

from pycelonis import get_celonis as pycelonis_get_celonis
from pycelonis import oauth2
from pycelonis.celonis import Celonis
from pycelonis_core.client import KeyType


@functools.cache
def get_celonis(
    base_url: Union[str, None] = None,
) -> Celonis:
    """Return a cached OAuth-authenticated pycelonis client.

    This mirrors the authentication flow used by the working augmentation
    table notebook.  ``pycelonis`` does not consume ``OAUTH_CLIENT_*``
    variables itself, so the OAuth token callback must be built explicitly.
    """
    resolved_base_url = (base_url or os.environ.get("CELONIS_URL", "")).strip("/")
    if not resolved_base_url:
        raise RuntimeError("CELONIS_URL must be provided to use the pycelonis client.")

    oauth_values = {
        "OAUTH_CLIENT_ID": os.environ.get("OAUTH_CLIENT_ID", ""),
        "OAUTH_CLIENT_SECRET": os.environ.get("OAUTH_CLIENT_SECRET", ""),
        "OAUTH_SCOPES": os.environ.get("OAUTH_SCOPES", ""),
    }
    missing = [name for name, value in oauth_values.items() if not value]
    if missing:
        raise RuntimeError(
            f"{', '.join(missing)} must be provided to use the pycelonis client."
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
