import subprocess
import sys

from celofast.sdk import Capture, Source
from celofast.sdk.generate import generate


def test_static_analyzer_resolves_generated_attribute_types(tmp_path):
    capture = Capture.create(
        Source(
            tenant_id="t",
            space_id="s",
            package_id="p",
            key="inventory-km",
            mode="draft",
        ),
        {
            "records": [
                {
                    "id": "Plant",
                    "attributes": [
                        {"id": "Number", "columnType": "string", "pql": "'123'"}
                    ],
                }
            ]
        },
    )
    package = tmp_path / "inventory"
    package.mkdir()
    for name, data in generate(capture).items():
        (package / name).write_bytes(data)
    consumer = tmp_path / "consumer.py"
    prefix = """from inventory import CapturedKnowledgeModel, Records, RecordsPlant, km as inventory_km
from typing_extensions import assert_type
from typing import Any
from celofast.sdk.objects import Attribute
from celofast.resources.knowledge_model import KnowledgeModelHandle
from celofast import CeloFast, Query, QueryDefinition
def needs_string(value: Attribute[str]) -> None: ...
def needs_integer(value: Attribute[int]) -> None: ...
assert_type(inventory_km, CapturedKnowledgeModel)
assert_type(inventory_km.records, Records)
assert_type(inventory_km.records.plant, RecordsPlant)
assert_type(inventory_km.records.plant.number, Attribute[str])
assert_type(inventory_km.records.plant["Number"], Attribute[Any])
assert_type(inventory_km.records.plant.get_attribute("Number"), Attribute[Any])
assert_type(next(iter(inventory_km.records.plant)), Attribute[Any])
attribute = inventory_km.records.plant.number
needs_string(attribute)
needs_string(inventory_km.records.plant.number)
cf = CeloFast("s", "p")
connected: KnowledgeModelHandle = cf.km(inventory_km)
by_key: KnowledgeModelHandle = cf.km("inventory-km")
built: Query = (
    connected.select(number=inventory_km.records.plant.number)
    .order_by(inventory_km.records.plant.number.desc())
)
record_query: Query = connected.select(inventory_km.records.plant)
filtered: Query = record_query.where(inventory_km.records.plant.number.eq("123"))
query: QueryDefinition = {"columns": {"Number": attribute}, "order_by": [{"pql": attribute}]}
"""
    consumer.write_text(prefix)
    command = [
        sys.executable,
        "-m",
        "mypy",
        "--follow-imports=silent",
        "--ignore-missing-imports",
        "--cache-dir",
        str(tmp_path / "mypy-cache"),
        str(package / "__init__.py"),
        str(consumer),
    ]
    good = subprocess.run(
        command, capture_output=True, text=True, timeout=60, check=False
    )
    assert good.returncode == 0, good.stdout + good.stderr
    consumer.write_text(prefix + "needs_integer(inventory_km.records.plant.number)\n")
    bad = subprocess.run(
        command, capture_output=True, text=True, timeout=60, check=False
    )
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert 'expected "Attribute[int]"' in bad.stdout
    consumer.write_text(prefix + "inventory_km.records.plant.number.eq(123)\n")
    bad_comparison = subprocess.run(
        command, capture_output=True, text=True, timeout=60, check=False
    )
    assert bad_comparison.returncode == 1, bad_comparison.stdout + bad_comparison.stderr
    assert 'expected "str | None"' in bad_comparison.stdout
    consumer.write_text(prefix + "inventory_km.records.plant.number = attribute\n")
    bad_assignment = subprocess.run(
        command, capture_output=True, text=True, timeout=60, check=False
    )
    assert bad_assignment.returncode == 1, bad_assignment.stdout + bad_assignment.stderr
    assert 'read-only' in bad_assignment.stdout
    consumer.write_text(prefix + "inventory_km.records.plant.attributes\n")
    old_navigation = subprocess.run(
        command, capture_output=True, text=True, timeout=60, check=False
    )
    assert old_navigation.returncode == 1, old_navigation.stdout + old_navigation.stderr
    assert 'has no attribute "attributes"' in old_navigation.stdout
    consumer.write_text(prefix + "connected.records\ninventory_km.select(number=attribute)\n")
    bad_interface = subprocess.run(
        command, capture_output=True, text=True, timeout=60, check=False
    )
    assert bad_interface.returncode == 1, bad_interface.stdout + bad_interface.stderr
    assert 'has no attribute "records"' in bad_interface.stdout
    assert 'has no attribute "select"' in bad_interface.stdout
