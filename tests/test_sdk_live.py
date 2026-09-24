"""Opt-in read-only integration checks; never author or update cloud KM items.

Set CELOFAST_LIVE_KM=1, CELOFAST_LIVE_SPACE_ID, CELOFAST_LIVE_PACKAGE_ID,
CELOFAST_LIVE_KM_KEY, CELOFAST_LIVE_RECORD_ID, and CELOFAST_LIVE_KEY_ID (the
attribute ID that identifies that record's objects). Every other record is
excluded. Use normal Celofast OAuth environment configuration.
"""

import importlib.util
import os
import sys

import pytest

from celofast import CeloFast
from celofast.sdk.capture import retrieve
from celofast.sdk.mapping import normalize, parse_mapping
from celofast.sdk.package import write_package

pytestmark = pytest.mark.skipif(
    os.environ.get("CELOFAST_LIVE_KM") != "1",
    reason="Live KM validation is explicitly opt-in",
)


@pytest.fixture(scope="module")
def live_context():
    cf = CeloFast(
        os.environ["CELOFAST_LIVE_SPACE_ID"], os.environ["CELOFAST_LIVE_PACKAGE_ID"]
    )
    native = cf._resolver.knowledge_model(os.environ["CELOFAST_LIVE_KM_KEY"])
    capture = retrieve(
        native,
        space_id=os.environ["CELOFAST_LIVE_SPACE_ID"],
        package_id=os.environ["CELOFAST_LIVE_PACKAGE_ID"],
        mode="draft",
    )
    record_id = os.environ["CELOFAST_LIVE_RECORD_ID"]
    record = next(r for r in capture.definition["records"] if r.get("id") == record_id)
    others = [r["id"] for r in capture.definition["records"] if r.get("id") != record_id]
    # Load only typed attributes with expressions; the rest are excluded explicitly.
    loadable = [
        a["id"] for c in ("attributes", "newAttributes", "augmentedAttributes")
        for a in record.get(c) or () if a.get("pql") and a.get("columnType")
    ]
    all_ids = [
        a["id"] for c in ("attributes", "newAttributes", "augmentedAttributes")
        for a in record.get(c) or () if a.get("id")
    ]
    mapping = parse_mapping({
        "exclude": others,
        "objects": {record_id: {
            "class": "LiveObject",
            "key": [os.environ["CELOFAST_LIVE_KEY_ID"]],
            "exclude-fields": sorted(set(all_ids) - set(loadable)),
        }},
    })
    normalize(capture, mapping)
    return cf, capture, mapping


def test_live_pull_import_and_object_page(live_context, tmp_path):
    cf, capture, mapping = live_context
    output = tmp_path / "inventory"
    write_package(capture, output, mapping=mapping)
    assert not write_package(capture, output, mapping=mapping, check=True)
    spec = importlib.util.spec_from_file_location(
        "live_generated_inventory", output / "__init__.py",
        submodule_search_locations=[str(output)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        client = cf.km(module.km)
        page = client.objects(module.LiveObject).fetch_page(page_size=2)
        assert all(isinstance(item, module.LiveObject) for item in page.items)
        if page.items:
            first = page.items[0]
            assert client.objects(module.LiveObject).get(first.key) == first
    finally:
        for name in [n for n in sys.modules if n.split(".")[0] == spec.name]:
            del sys.modules[name]
