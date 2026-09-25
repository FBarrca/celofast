"""Shared live-test setup using the repository's application configuration."""

import importlib
import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

from celofast.cli import main as celofast_cli

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def live_credentials():
    load_dotenv(ROOT / ".env")
    required = ("CELONIS_URL", "OAUTH_CLIENT_ID", "OAUTH_CLIENT_SECRET", "OAUTH_SCOPES")
    if not all(os.environ.get(name) for name in required):
        pytest.skip("Live tests need CELONIS_URL and OAUTH_* credentials (.env)")


@pytest.fixture(scope="module")
def inventory_package(live_credentials, tmp_path_factory):
    """Pull the configured inventory KM into a temporary, importable package."""
    root = tmp_path_factory.mktemp("pulled")
    output = root / "generated" / "inventory"
    pull = ["km", "pull", "inventory", "--project", str(ROOT / "pyproject.toml"),
            "--output", str(output)]
    assert celofast_cli(pull) == 0
    assert celofast_cli([*pull, "--check"]) == 0

    def purge():
        for name in list(sys.modules):
            if name.split(".")[0] == "generated":
                del sys.modules[name]

    purge()
    try:
        sys.path.insert(0, str(root))
        try:
            package = importlib.import_module("generated.inventory")
        finally:
            sys.path.remove(str(root))
        assert Path(package.__file__).parent == output
        yield package
    finally:
        purge()
