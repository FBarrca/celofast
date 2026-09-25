"""Read-only integration checks using .env and the inventory KM in pyproject.toml.

Run when normal Celofast OAuth credentials are configured. Exclude with
``uv run pytest -m "not live"``. Never author or update cloud KM items.
"""

import pytest

from celofast import CeloFast

pytestmark = pytest.mark.live


def test_live_pull_import_and_object_page(inventory_package):
    module = inventory_package
    source = module.km.source
    cf = CeloFast(source.space_id, source.package_id, mode=source.mode)
    client = cf.km(module.km)
    page = client.objects(module.Plant).fetch_page(page_size=2)
    assert all(isinstance(item, module.Plant) for item in page.items)
    if page.items:
        first = page.items[0]
        assert client.objects(module.Plant).get(first.key) == first
