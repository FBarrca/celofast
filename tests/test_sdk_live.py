"""Opt-in read-only integration checks; never author or update cloud KM items.

Set CELOFAST_LIVE_KM=1, CELOFAST_LIVE_SPACE_ID, CELOFAST_LIVE_PACKAGE_ID,
CELOFAST_LIVE_KM_KEY, CELOFAST_LIVE_RECORD_ID, and CELOFAST_LIVE_ATTRIBUTE_ID.
Use normal Celofast OAuth environment configuration for authentication.
"""

import importlib.util
import os
import sys

import pytest

from celofast import CeloFast
from celofast.sdk import KPI, Capture, KnowledgeModel
from celofast.sdk.capture import retrieve
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
    key = os.environ["CELOFAST_LIVE_KM_KEY"]
    native = cf._resolver.knowledge_model(key)
    capture = retrieve(
        native,
        space_id=os.environ["CELOFAST_LIVE_SPACE_ID"],
        package_id=os.environ["CELOFAST_LIVE_PACKAGE_ID"],
        mode="draft",
    )
    path = (
        "records",
        os.environ["CELOFAST_LIVE_RECORD_ID"],
        "attributes",
        os.environ["CELOFAST_LIVE_ATTRIBUTE_ID"],
    )
    return cf, capture, path


def test_live_pull_import_and_captured_attribute_query(live_context, tmp_path):
    cf, capture, path = live_context
    output = tmp_path / "inventory"
    write_package(capture, output)
    assert not write_package(capture, output, check=True)
    spec = importlib.util.spec_from_file_location(
        "live_generated_inventory", output / "__init__.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        assert module.km.capture == capture
        record = module.km.records[path[1]]
        attribute = record.attributes[path[3]]
        result = cf.km(module.km).execute({"columns": {"Anchor": attribute}}, limit=1)
        assert len(result) == 1
        assert list(result.columns) == ["Anchor"]
    finally:
        sys.modules.pop(spec.name, None)


@pytest.mark.parametrize("dependency", ["kpi", "column"])
def test_live_unresolved_dependencies_fail(live_context, dependency):
    from saolapy.errors import DataExportFailedError

    cf, capture, path = live_context
    layer = capture.to_dict()
    missing = "CELOFAST_MISSING_3F6DB6908A"
    if dependency == "kpi":
        expression = f'KPI("{missing}")'
    else:
        # A unique physical table/column reference cannot resolve in the DM.
        expression = f'"{missing}"."{missing}"'
    layer["kpis"] = [{"id": "sdk_probe_missing", "type": "KPI", "pql": expression}]
    variant = Capture.create(capture.source, layer)
    with pytest.raises(DataExportFailedError, match=missing):
        cf.km(KnowledgeModel(variant)).execute(
            {
                "columns": {
                    "Probe": KPI(variant, ("kpis", "sdk_probe_missing")),
                    "Anchor": Attribute(variant, path),
                }
            },
            limit=1,
        )
