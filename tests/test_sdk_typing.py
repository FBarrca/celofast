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
from celofast import QueryDefinition
def needs_string(value: Attribute[str]) -> None: ...
def needs_integer(value: Attribute[int]) -> None: ...
attribute = inventory_km.records.plant.attributes.number
needs_string(attribute)
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
    consumer.write_text(prefix + "needs_integer(attribute)\n")
    bad = subprocess.run(
        command, capture_output=True, text=True, timeout=60, check=False
    )
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert 'expected "Attribute[int]"' in bad.stdout
