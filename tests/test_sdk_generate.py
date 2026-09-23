import ast
import dataclasses
import json
import subprocess
import sys
from datetime import date

import pytest

from celofast.exceptions import ObjectMappingError
from celofast.sdk import Field, ObjectModel
from celofast.sdk.generate import PACKAGE_FILES, generate
from celofast.sdk.mapping import _names, normalize

from objects_fixture import MAPPING, attribute, capture, load, write


def record(layer, record_id):
    return next(item for item in layer["records"] if item["id"] == record_id)


def test_package_layout_and_offline_import(tmp_path):
    files = generate(capture(), MAPPING)
    assert tuple(sorted(files)) == tuple(sorted(PACKAGE_FILES))
    package = write(tmp_path / "inventory")
    # Importing generated classes never loads the PyCelonis query stack.
    script = (
        "import sys, importlib.util;"
        f"spec=importlib.util.spec_from_file_location('inv', {str(package / '__init__.py')!r},"
        f" submodule_search_locations=[{str(package)!r}]);"
        "m=importlib.util.module_from_spec(spec); sys.modules['inv']=m; spec.loader.exec_module(m);"
        "assert not any(k.startswith(('pycelonis', 'saolapy', 'pandas')) for k in sys.modules), "
        "sorted(k for k in sys.modules if k.startswith(('pycelonis','saolapy','pandas')));"
        "print(m.__all__)"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "Plant" in result.stdout and "km" in result.stdout


def test_value_classes_and_definitions_are_separate(tmp_path):
    module = load(write(tmp_path / "inventory"))
    Plant, Material, StockLine = module.Plant, module.Material, module.StockLine

    assert isinstance(module.km, ObjectModel)
    assert list(module.km) == [Material, Plant, StockLine]
    assert module.km["O_PLANT"] is Plant
    assert module.__all__ == ["Material", "Plant", "StockLine", "km"]

    # Plant.fields describes the type; its members are typed Field definitions.
    definition = Plant.fields
    assert definition.object_type == "O_PLANT"
    assert isinstance(definition.country, Field)
    assert definition.country.id == "COUNTRY"
    assert definition["Description"] is definition.description
    assert [f.name for f in definition.key_fields] == ["id"]
    assert [f.name for f in definition] == ["id", "country", "plantnumber", "opened", "description"]
    assert definition.links["materials"].target == "O_MATERIAL"
    assert definition.id.nullable is False and definition.country.nullable is True

    # Plant describes one loaded object: plain values plus key.
    names = [f.name for f in dataclasses.fields(Plant)]
    assert names == ["key", "id", "country", "plantnumber", "opened", "description"]
    plant = Plant(key="P1", id="P1", country="DE", plantnumber=None, opened=date(2020, 1, 1), description="x")
    assert plant.country == "DE" and plant.plantnumber is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        plant.country = "FR"
    assert plant.ref.object_type == "O_PLANT" and plant.ref.key == "P1"
    assert plant.ref.source == module.km.source
    assert plant == Plant(key="P1", id="P1", country="DE", plantnumber=None, opened=date(2020, 1, 1), description="x")
    assert dataclasses.asdict(plant) == {
        "key": "P1", "id": "P1", "country": "DE", "plantnumber": None,
        "opened": date(2020, 1, 1), "description": "x",
    }
    assert "_context" not in repr(plant)

    assert StockLine.fields.object_type == "O_STOCK"
    assert [f.name for f in StockLine.fields.key_fields] == ["plant_id", "day"]
    assert Material.fields.untyped.value_type == "str"


def test_generated_source_declares_explicit_types(tmp_path):
    files = generate(capture(), MAPPING)
    objects = files["objects.py"].decode()
    tree = ast.parse(objects)
    stock = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "StockLine")
    annotations = {
        n.target.id: ast.unparse(n.annotation) for n in stock.body if isinstance(n, ast.AnnAssign)
    }
    assert annotations["key"] == "tuple[str, _dt.date]"
    assert annotations["plant_id"] == "str"
    assert annotations["qty"] == "int | None"
    assert annotations["fields"] == "ClassVar[_defs.StockLineDefinition]"
    definitions = files["definitions.py"].decode()
    assert "country: _d.Field[str | None]" in definitions
    assert "id: _d.Field[str]" in definitions
    links = files["links.py"].decode()
    assert "def plant(self) -> _o.ToOne[_objects.Plant]:" in links
    assert "def materials(self) -> _o.ObjectCollection[_objects.Material]:" in links


def test_package_is_self_contained_python(tmp_path):
    files = generate(capture(), MAPPING)
    assert not [name for name in files if name.endswith(".json")]
    module = load(write(tmp_path / "inventory"))

    # Everything the runtime needs is written as literals in the code.
    info = module.km.info
    assert info.source == capture().source
    assert info.data_model_id == "dm"
    assert module.km.variables == ("factor",)  # Used by Material.stock's expression.
    country = module.Plant.fields.country
    assert (country.id, country.expression, country.value_type) == (
        "COUNTRY", '"o_Plant"."Country"', "str",
    )
    assert module.Plant.fields.metadata == {"displayName": "Plant", "description": None}
    assert module.Plant.fields.model is info is module.Material.fields.model

    # The stamp identifies generated output and its source; nothing else.
    assert module.__celofast__ == {
        "managed_by": "celofast.km",
        "source": capture().source.model_dump(),
    }


def test_variables_in_comments_are_not_reported(tmp_path):
    layer = capture().to_dict()
    record(layer, "O_PLANT")["attributes"][1]["pql"] = '"o_Plant"."Country" -- was ${old}'
    from celofast.sdk import Capture

    module = load(write(tmp_path / "commented", Capture.create(capture().source, layer)))
    assert module.km.variables == ("factor",)


def test_generation_is_deterministic():
    assert generate(capture(), MAPPING) == generate(capture(), MAPPING)


def test_unidentified_records_require_mapping_or_exclusion():
    with pytest.raises(ObjectMappingError) as error:
        generate(capture(), {})
    message = str(error.value)
    assert "O_MATERIAL (map it under objects or add it to exclude): no declared identifier" in message
    assert "O_STOCK" in message and "EL_LOG" in message
    # Records with a declared identifier matching one attribute need no mapping.
    assert "O_PLANT" not in message


def test_unknown_types_and_missing_expressions_are_never_weakened():
    mapping = json.loads(json.dumps(MAPPING))
    del mapping["objects"]["O_MATERIAL"]["types"]
    with pytest.raises(ObjectMappingError, match="'UNTYPED' has unknown type None"):
        normalize(capture(), mapping)
    mapping["objects"]["O_MATERIAL"]["exclude-fields"] = ["UNTYPED"]
    spec = normalize(capture(), mapping)
    material = next(o for o in spec.objects if o.record_id == "O_MATERIAL")
    assert "UNTYPED" not in {f.attribute_id for f in material.fields}

    layer_capture = capture()
    layer = layer_capture.to_dict()
    record(layer, "O_STOCK")["attributes"].append({"id": "EMPTY", "columnType": "STRING"})
    from celofast.sdk import Capture

    with pytest.raises(ObjectMappingError, match="'EMPTY' has no expression"):
        normalize(Capture.create(layer_capture.source, layer), MAPPING)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"key": ["COUNT"], "types": {"UNTYPED": "str", "COUNT": "float"}}, "keys need"),
        ({"key": ["MISSING"]}, "not a loaded field"),
        ({"key": ["ID", "ID"]}, "repeats"),
        ({"exclude-fields": ["NOPE"], "key": ["ID"]}, "unknown attribute 'NOPE'"),
    ],
)
def test_keys_are_verified(change, message):
    mapping = json.loads(json.dumps(MAPPING))
    mapping["objects"]["O_MATERIAL"].update(change)
    with pytest.raises(ObjectMappingError, match=message):
        normalize(capture(), mapping)


def test_identifier_is_not_guessed_from_field_names():
    layer = capture().to_dict()
    record(layer, "O_PLANT")["identifier"] = {"pql": '"o_Plant"."Other"'}
    from celofast.sdk import Capture

    with pytest.raises(ObjectMappingError, match="O_PLANT: declared identifier matches no loaded attribute"):
        normalize(Capture.create(capture().source, layer), MAPPING)


@pytest.mark.parametrize(
    ("link", "message"),
    [
        ({"target": "O_STOCK", "cardinality": "one", "on": {"ID": "PLANT_ID"}}, "must map exactly the target key"),
        ({"target": "EL_LOG", "cardinality": "many", "on": {"ID": "ID"}}, "not a generated object type"),
        ({"target": "O_MATERIAL", "cardinality": "many", "on": {"OPENED": "PLANT_ID"}}, "different types"),
        ({"target": "O_MATERIAL", "cardinality": "many", "on": {"ID": "NOPE"}}, "loaded fields"),
    ],
)
def test_relationships_require_known_target_cardinality_and_mapping(link, message):
    mapping = json.loads(json.dumps(MAPPING))
    mapping["objects"]["O_PLANT"]["links"]["broken"] = link
    with pytest.raises(ObjectMappingError, match=message):
        normalize(capture(), mapping)


def test_invalid_mapping_documents_and_names_fail_clearly():
    with pytest.raises(ObjectMappingError, match="Invalid KM object mapping"):
        normalize(capture(), {"objects": {"O_PLANT": {"unknown": 1}}})
    mapping = json.loads(json.dumps(MAPPING))
    mapping["objects"]["O_STOCK"]["class"] = "Plant"
    with pytest.raises(ObjectMappingError, match="class name 'Plant' is also used by O_PLANT"):
        normalize(capture(), mapping)
    mapping["objects"]["O_STOCK"]["class"] = "not a class"
    with pytest.raises(ObjectMappingError, match="capitalized Python identifier"):
        normalize(capture(), mapping)
    mapping = json.loads(json.dumps(MAPPING))
    mapping["exclude"].append("O_STOCK")
    mapping["objects"]["MISSING"] = {"key": ["ID"]}
    with pytest.raises(ObjectMappingError) as error:
        normalize(capture(), mapping)
    assert "O_STOCK: both mapped and excluded" in str(error.value)
    assert "MISSING: mapped or excluded, but no such record" in str(error.value)


def test_reserved_and_colliding_names_get_readable_suffixes(tmp_path):
    layer = capture().to_dict()
    plant = record(layer, "O_PLANT")
    plant["attributes"] += [
        attribute("KEY", '"o_Plant"."Key"'),
        attribute("Links", '"o_Plant"."Links"'),
        attribute("date", '"o_Plant"."D"', "DATE"),
        attribute("Country", '"o_Plant"."C1"'),
    ]
    plant["newAttributes"] = [attribute("Region", '"o_Plant"."R"')]
    from celofast.sdk import Capture

    module = load(write(tmp_path / "names", Capture.create(capture().source, layer)))
    names = [f.name for f in module.Plant.fields]
    assert {"key_attribute", "links_attribute", "date", "region"} <= set(names)
    assert {"country_attribute_1", "country_attribute_2"} <= set(names)
    assert module.Plant.fields["Country"].name != module.Plant.fields["COUNTRY"].name


def test_an_id_in_several_collections_must_be_excluded():
    layer = capture().to_dict()
    record(layer, "O_PLANT")["newAttributes"] = [attribute("COUNTRY", '"o_Plant"."C2"')]
    from celofast.sdk import Capture

    changed = Capture.create(capture().source, layer)
    with pytest.raises(ObjectMappingError, match="'COUNTRY' is defined in several collections"):
        normalize(changed, MAPPING)
    mapping = json.loads(json.dumps(MAPPING))
    mapping["objects"]["O_PLANT"]["exclude-fields"] = ["COUNTRY"]
    plant = next(o for o in normalize(changed, mapping).objects if o.record_id == "O_PLANT")
    assert "COUNTRY" not in {f.attribute_id for f in plant.fields}
    ids = ["ID", "ID_ATTRIBUTE", "ID_ATTRIBUTE_1", "NumberName", "number_name", "KEY"]
    assert _names(ids, {"id", "key"}, suffixes=["attribute"] * 6) == [
        "id_attribute_2", "id_attribute", "id_attribute_1",
        "number_name_attribute_1", "number_name_attribute_2", "key_attribute",
    ]