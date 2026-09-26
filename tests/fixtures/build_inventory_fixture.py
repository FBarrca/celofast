"""Refresh tests/fixtures/inventory_km.json from the live Inventory KM.

Run from the repository root with Celonis credentials configured (.env):
    uv run python tests/fixtures/build_inventory_fixture.py

Captures the KM configured as `inventory` in pyproject.toml exactly as
`celofast km pull` does (Data Model tables, foreign keys, and pull-time
validation), keeps the records of the object types the offline tests use
(with only the metadata generation needs), reduces other records to stubs,
and replaces tenant identifiers so the fixture contains no tenant data.
"""

import json

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from celofast import CeloFast
from celofast.cli import _Progress
from celofast.sdk.capture import record_table, retrieve
from celofast.sdk.model import normalize
from celofast.sdk.validation import object_links, resolve_types, validate

USED = {
    "MaterialMasterPlant",
    "PlannedSupply",
    "Plant",
    "PurchaseDocument",
    "PurchaseDocumentLine",
    "PurchaseScheduleLine",
    "Vendor",
}

settings = tomllib.load(open("pyproject.toml", "rb"))["tool"]["celofast"]["knowledge-models"]["inventory"]
cf = CeloFast(settings["space-id"], settings["package-id"], mode=settings["mode"])
native = cf._resolver.knowledge_model(settings["key"])
progress = _Progress()
try:
    capture = retrieve(
        native,
        data_model=cf._resolver.data_model(native),
        space_id=settings["space-id"],
        package_id=settings["package-id"],
        mode=settings["mode"],
        progress=progress,
    )
    connection = cf._km_connection(settings["key"])
    capture = resolve_types(capture, connection._type_of, progress=progress)
    capture = validate(capture, connection._probe, progress=progress)
    capture = object_links(capture, connection._probe, progress=progress)
finally:
    progress.close()

real = json.loads(capture.model_dump_json())
specs = [spec for spec in normalize(capture).objects if spec.class_name in USED]
keep = {spec.record_id for spec in specs}
expressions = {field.expression for spec in specs for field in spec.fields}
assert len(keep) == len(USED), keep
KEEP_KEYS = {
    "id", "displayName", "description", "type", "pql", "columnName", "columnType",
    "identifier", "isActivityTable",
}


def trim(item):
    return {k: v for k, v in item.items() if k in KEEP_KEYS}


records = []
tables = set()
for record in capture.definition["records"]:
    if record["id"] in keep:
        trimmed = trim(record)
        for collection in ("attributes", "newAttributes", "augmentedAttributes"):
            trimmed[collection] = [trim(attribute) for attribute in record.get(collection) or ()]
        records.append(trimmed)
        tables.add(record_table(record["pql"]).lower())
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
    "input_variables": real.get("input_variables", {}),
    "types": {expression: type_ for expression, type_ in real.get("types", {}).items()
              if expression in expressions},
    # Data Model catalog metadata (no tenant data): the kept records' tables
    # and the foreign keys between them.
    "tables": {name: table for name, table in real["tables"].items() if name.lower() in tables},
    "joins": [join for join in real["joins"] if join["one"].lower() in tables and join["many"].lower() in tables],
    "validation": {rid: rejected for rid, rejected in real["validation"].items() if rid in keep},
}
with open("tests/fixtures/inventory_km.json", "w", encoding="utf-8", newline="\n") as stream:
    json.dump(fixture, stream, indent=1, ensure_ascii=False, sort_keys=True)
    stream.write("\n")
print("records", len(records), "kept", len(keep), "tables", len(fixture["tables"]))
