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
    prefix = """from inventory import km as inventory_km
from celofast.sdk.objects import Attribute
from celofast import CeloFast, Query, QueryDefinition
def needs_string(value: Attribute[str]) -> None: ...
def needs_integer(value: Attribute[int]) -> None: ...
attribute = inventory_km.records.plant.attributes.number
needs_string(attribute)
needs_string(inventory_km.records.plant.number)
cf = CeloFast("s", "p")
connected = cf.km(inventory_km)
needs_string(connected.records.plant.number)
built: Query = (
    connected.select(number=connected.records.plant.number)
    .order_by(connected.records.plant.number.desc())
)
record_query: Query = connected.select(connected.records.plant)
filtered: Query = record_query.where(connected.records.plant.number.eq("123"))
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
        str(consumer),
    ]
    good = subprocess.run(
        command, capture_output=True, text=True, timeout=60, check=False
    )
    assert good.returncode == 0, good.stdout + good.stderr
    consumer.write_text(prefix + "needs_integer(connected.records.plant.number)\n")
    bad = subprocess.run(
        command, capture_output=True, text=True, timeout=60, check=False
    )
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert 'expected "Attribute[int]"' in bad.stdout
    consumer.write_text(prefix + "connected.records.plant.number.eq(123)\n")
    bad_comparison = subprocess.run(
        command, capture_output=True, text=True, timeout=60, check=False
    )
    assert bad_comparison.returncode == 1, bad_comparison.stdout + bad_comparison.stderr
    assert 'expected "str | None"' in bad_comparison.stdout
