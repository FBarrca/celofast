"""A small generated inventory package shared by object SDK tests."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from celofast.sdk import Capture, Source
from celofast.sdk.generate import generate

SOURCE = Source(
    tenant_id="tenant",
    space_id="space",
    package_id="package",
    key="inventory-km",
    mode="draft",
)


def attribute(id_, pql, column_type="STRING", **extra):
    return {"id": id_, "pql": pql, "columnType": column_type, "type": "ATTRIBUTE", **extra}


def capture(**changes):
    layer = {
        "tenantId": "tenant",
        "dataModelId": "dm",
        "metadata": {"key": SOURCE.key},
        "records": [
            {
                "id": "O_PLANT",
                "displayName": "Plant",
                "pql": '"o_Plant"',
                "identifier": {"id": "Plant_ID", "pql": '"o_Plant"."ID"\n'},
                "attributes": [
                    attribute("ID", '"o_Plant"."ID"'),
                    attribute("COUNTRY", '"o_Plant"."Country"'),
                    attribute("PLANTNUMBER", '"o_Plant"."Number"', "string"),
                    attribute("OPENED", '"o_Plant"."Opened"', "DATE"),
                    attribute("Description", '"o_Plant"."Text"'),
                ],
            },
            {
                "id": "O_MATERIAL",
                "displayName": "Material",
                "pql": '"o_Material"',
                "attributes": [
                    attribute("ID", '"o_Material"."ID"'),
                    attribute("PLANT_ID", '"o_Material"."Plant_ID"'),
                    attribute("STOCK", '"o_Material"."Stock" * ${factor}', "FLOAT"),
                    attribute("ACTIVE", '"o_Material"."Active"', "BOOLEAN"),
                    attribute("UPDATED", '"o_Material"."Updated"', "DATETIME"),
                    attribute("COUNT", '"o_Material"."Count"', "INTEGER"),
                    attribute("UNTYPED", '"o_Material"."X"', None),
                ],
            },
            {
                "id": "O_STOCK",
                "displayName": "Stock Line",
                "pql": '"o_Stock"',
                "attributes": [
                    attribute("PLANT_ID", '"o_Stock"."Plant_ID"'),
                    attribute("DAY", '"o_Stock"."Day"', "DATE"),
                    attribute("QTY", '"o_Stock"."Qty"', "INTEGER"),
                ],
            },
            {"id": "EL_LOG", "displayName": "Event log", "attributes": []},
        ],
        "kpis": [{"id": "Value", "pql": "SUM(1)"}],
        **changes,
    }
    # The Data Model joins plants to materials; stock lines have no foreign key,
    # so Plant.links.stock is traversal-only.
    return Capture.create(SOURCE, layer, joins=JOINS)


JOINS = [{"one": "o_Plant", "many": "o_Material", "columns": [["ID", "Plant_ID"]]}]


MAPPING = {
    "exclude": ["EL_LOG"],
    "objects": {
        "O_PLANT": {
            "links": {
                "materials": {
                    "target": "O_MATERIAL",
                    "cardinality": "many",
                    "on": {"ID": "PLANT_ID"},
                },
                "stock": {
                    "target": "O_STOCK",
                    "cardinality": "many",
                    "on": {"ID": "PLANT_ID"},
                },
            }
        },
        "O_MATERIAL": {
            "key": ["ID"],
            "types": {"UNTYPED": "str"},
            "links": {
                "plant": {"target": "O_PLANT", "cardinality": "one", "on": {"PLANT_ID": "ID"}},
            },
        },
        "O_STOCK": {"class": "StockLine", "key": ["PLANT_ID", "DAY"]},
    },
}


def write(directory: Path, capture_=None, mapping=MAPPING) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in generate(capture_ or capture(), mapping).items():
        (directory / name).write_bytes(data)
    return directory


def load(directory: Path, name: str = "inventory_sdk") -> ModuleType:
    """Import a generated package directory under a unique module name."""
    for module in [key for key in sys.modules if key == name or key.startswith(name + ".")]:
        sys.modules.pop(module)
    spec = importlib.util.spec_from_file_location(
        name, directory / "__init__.py", submodule_search_locations=[str(directory)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
