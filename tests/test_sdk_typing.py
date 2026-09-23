import subprocess
import sys

from objects_fixture import write

PREFIX = """from datetime import date
from typing_extensions import assert_type
from celofast import CeloFast, KnowledgeModelClient
from celofast.sdk import Field, ObjectCollection, ObjectModel, ObjectPage, ObjectRef, ToOne
from inventory import Material, Plant, StockLine, km as inventory

assert_type(inventory, ObjectModel)
assert_type(Plant.fields.country, Field[str | None])
assert_type(Plant.fields.id, Field[str])
cf = CeloFast("s", "p")
client: KnowledgeModelClient = cf.km(inventory, variables={"factor": "2"})
plants = client.objects(Plant)
assert_type(plants, ObjectCollection[Plant])
plant = plants.get("P1")
assert_type(plant, Plant)
assert_type(plant.country, str | None)
assert_type(plant.opened, date | None)
assert_type(plant.key, str)
assert_type(plant.ref, ObjectRef)
page = plants.where(Plant.fields.country.eq("DE")).fetch_page(page_size=100)
assert_type(page, ObjectPage[Plant])
assert_type(page.items[0], Plant)
assert_type(plant.links.materials, ObjectCollection[Material])
assert_type(plant.links.materials.fetch_page(), ObjectPage[Material])
material = plant.links.materials.fetch_page().items[0]
assert_type(material.links.plant, ToOne[Plant])
assert_type(material.links.plant.fetch(), Plant | None)
line = client.objects(StockLine).get(("P1", date(2024, 1, 1)))
assert_type(line.key, tuple[str, date])
from celofast.sdk import Predicate, ToManyRelation, ToOneRelation
assert_type(Plant.relations.materials, ToManyRelation[Material])
assert_type(Material.relations.plant, ToOneRelation[Plant])
rule: Predicate = (
    Plant.fields.country.ne("FR")
    & Plant.fields.opened.gte(date(2020, 1, 1))
    & ~Plant.relations.materials.any(Material.fields.stock.lt(Material.fields.count))
)
ordered = plants.where(rule).order_by(Plant.fields.opened.desc(), Plant.fields.country)
assert_type(ordered, ObjectCollection[Plant])
assert_type(Material.relations.plant.has(Plant.fields.country.eq("DE")), Predicate)
"""


def run_mypy(tmp_path, source):
    consumer = tmp_path / "consumer.py"
    consumer.write_text(source)
    return subprocess.run(
        [
            sys.executable, "-m", "mypy", "--follow-imports=silent",
            "--ignore-missing-imports", "--cache-dir", str(tmp_path / "mypy-cache"),
            str(tmp_path / "inventory"), str(consumer),
        ],
        capture_output=True, text=True, timeout=120, check=False, cwd=tmp_path,
    )


def test_static_analyzer_sees_values_definitions_and_links(tmp_path):
    write(tmp_path / "inventory")
    good = run_mypy(tmp_path, PREFIX)
    assert good.returncode == 0, good.stdout + good.stderr

    cases = {
        "Plant.fields.country.eq(123)\n": 'Argument 1 to "eq" of "Field" has incompatible type "int"',
        "Plant.fields.id.eq(None)\n": 'incompatible type "None"',
        "plant.country = 'FR'\n": "read-only",
        "plant.links.materials.fetch()\n": 'has no attribute "fetch"',
        "client.select(Plant)\n": 'has no attribute "select"',
        "client.execute({})\n": 'has no attribute "execute"',
        "Plant.fields.opened.lt('2020-01-01')\n": 'Argument 1 to "lt" of "Field" has incompatible type "str"',
        "Plant.relations.materials.has()\n": 'has no attribute "has"',
        "Material.relations.plant.any()\n": 'has no attribute "any"',
        "inventory.records\n": 'has no attribute "records"',
        "x: int = plant.country\n": "Incompatible types in assignment",
    }
    for line, expected in cases.items():
        bad = run_mypy(tmp_path, PREFIX + line)
        assert bad.returncode == 1, line + bad.stdout + bad.stderr
        assert expected in bad.stdout, line + bad.stdout
