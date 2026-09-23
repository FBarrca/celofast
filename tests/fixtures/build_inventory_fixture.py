"""Refresh tests/fixtures/inventory_km.json from the live Inventory KM.

Run from the repository root with Celonis credentials configured (.env):
    uv run python tests/fixtures/build_inventory_fixture.py

Captures the KM configured as `inventory` in pyproject.toml, keeps the records
mapped in inventory-objects.toml (with only the metadata generation needs),
reduces other records to stubs, and replaces tenant identifiers so the fixture
contains no tenant data.
"""

import json

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from celofast import CeloFast
from celofast.sdk.capture import retrieve

settings = tomllib.load(open("pyproject.toml", "rb"))["tool"]["celofast"]["knowledge-models"]["inventory"]
mapping = tomllib.load(open(settings["mapping"], "rb"))
cf = CeloFast(settings["space-id"], settings["package-id"], mode=settings["mode"])
capture = retrieve(
    cf._resolver.knowledge_model(settings["key"]),
    space_id=settings["space-id"],
    package_id=settings["package-id"],
    mode=settings["mode"],
)
real = {"definition": capture.to_dict()}
KEEP_KEYS = {"id", "displayName", "description", "type", "pql", "columnName", "columnType", "identifier"}


def trim(item):
    return {k: v for k, v in item.items() if k in KEEP_KEYS}


records = []
for record in real["definition"]["records"]:
    if record["id"] in mapping["objects"]:
        excluded = set(mapping["objects"][record["id"]].get("exclude-fields", []))
        trimmed = trim(record)
        for collection in ("attributes", "newAttributes", "augmentedAttributes"):
            items = []
            for attribute in record.get(collection) or ():
                attribute = trim(attribute)
                if attribute["id"] in excluded:
                    attribute.pop("pql", None)  # Not loaded; keep only its identity.
                items.append(attribute)
            trimmed[collection] = items
        records.append(trimmed)
    else:
        records.append({"id": record["id"], "displayName": record.get("displayName"), "type": "RECORD"})

fixture = {
    "format_version": 1,
    "source": {
        "tenant_id": "fixture-tenant",
        "space_id": "fixture-space",
        "package_id": "fixture-package",
        "key": "inventory-km",
        "mode": "draft",
    },
    "definition": {"dataModelId": "fixture-dm", "records": records},
}
with open("tests/fixtures/inventory_km.json", "w", encoding="utf-8", newline="\n") as stream:
    json.dump(fixture, stream, indent=1, ensure_ascii=False, sort_keys=True)
    stream.write("\n")
print("records", len(records))
