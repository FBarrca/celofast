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

from celofast.sdk import Capture

from objects_fixture import JOINS, MAPPING, TABLES, attribute, capture, load, write


def record(layer, record_id):
    return next(item for item in layer["records"] if item["id"] == record_id)


def rebuild(layer, *, joins=JOINS, tables=TABLES):
    """A capture of a changed layer with the fixture's Data Model metadata."""
    return Capture.create(capture().source, layer, joins=joins, tables=tables)


def spec(model, record_id):
    return next(o for o in model.objects if o.record_id == record_id)


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
    # Celonis DATE columns hold timestamps: they load as datetimes.
    assert annotations["key"] == "tuple[str, _dt.datetime]"
    assert annotations["day"] == "_dt.datetime"
    assert annotations["plant_id"] == "str"
    assert annotations["qty"] == "int | None"
    assert annotations["fields"] == "ClassVar[_defs.StockLineDefinition]"
    definitions = files["definitions.py"].decode()
    assert "country: _d.Field[str | None]" in definitions
    assert "id: _d.Field[str]" in definitions
    assert "day: _d.DateTimeField[_dt.datetime]" in definitions
    assert "opened: _d.Field[_dt.date | None]" in definitions  # types override
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
    module = load(write(tmp_path / "commented", rebuild(layer)))
    assert module.km.variables == ("factor",)


def test_generation_is_deterministic():
    assert generate(capture(), MAPPING) == generate(capture(), MAPPING)


def test_records_keys_and_types_are_derived_from_the_data_model():
    model = normalize(capture(), {})
    assert [(o.record_id, o.class_name, o.key) for o in model.objects] == [
        ("O_MATERIAL", "Material", ("id",)),
        ("O_PLANT", "Plant", ("id",)),
        ("O_STOCK", "Stock", ("plant_id", "day")),  # Class name from the table.
    ]
    types = {f.attribute_id: f.value_type for f in spec(model, "O_MATERIAL").fields}
    # Data Model column types win over the KM's declared (or missing) types.
    assert types == {
        "ID": "str", "PLANT_ID": "str", "ACTIVE": "bool", "UPDATED": "datetime",
        "COUNT": "int", "UNTYPED": "str",
    }
    assert {f.attribute_id: f.value_type for f in spec(model, "O_PLANT").fields}["OPENED"] == "datetime"
    diagnostics = "\n".join(model.diagnostics)
    assert "EL_LOG: no primary key or declared identifier; not an object type." in diagnostics
    assert "O_MATERIAL.STOCK: uses KM input variables; add it to include-fields" in diagnostics


def test_records_without_primary_key_or_that_are_event_logs_are_skipped():
    tables = {**TABLES, "o_Stock": {**TABLES["o_Stock"], "primary_key": []}}
    model = normalize(rebuild(capture().to_dict(), tables=tables), {})
    assert "O_STOCK" not in {o.record_id for o in model.objects}
    assert "O_STOCK: no primary key or declared identifier; not an object type." in model.diagnostics

    layer = capture().to_dict()
    record(layer, "O_STOCK")["isActivityTable"] = True
    model = normalize(rebuild(layer), {})
    assert "O_STOCK: event log; not an object type." in model.diagnostics


def test_unknown_types_and_missing_expressions_are_skipped_and_reported():
    layer = capture().to_dict()
    record(layer, "O_MATERIAL")["attributes"] += [
        attribute("CALC", 'CASE WHEN "o_Material"."Count" > 1 THEN 1 END', None),
        {"id": "EMPTY", "columnType": "STRING", "type": "ATTRIBUTE"},
    ]
    changed = rebuild(layer)
    model = normalize(changed, {})
    loaded = {f.attribute_id for f in spec(model, "O_MATERIAL").fields}
    assert not {"CALC", "EMPTY"} & loaded
    assert "O_MATERIAL.CALC: unknown type None; not generated." in model.diagnostics
    assert "O_MATERIAL.EMPTY: no expression; not generated." in model.diagnostics
    # An explicit type loads a calculated attribute the KM leaves untyped.
    model = normalize(changed, {"objects": {"O_MATERIAL": {"types": {"CALC": "int"}}}})
    assert {f.attribute_id: f.value_type for f in spec(model, "O_MATERIAL").fields}["CALC"] == "int"


def test_attributes_rejected_at_pull_are_skipped_and_reported():
    rejected = capture().with_validation({"O_MATERIAL": {"COUNT": "fails in Celonis: boom"}})
    model = normalize(rejected, {})
    assert "COUNT" not in {f.attribute_id for f in spec(model, "O_MATERIAL").fields}
    assert "O_MATERIAL.COUNT: fails in Celonis: boom; not generated." in model.diagnostics


def test_automatic_links_follow_foreign_keys():
    model = normalize(capture(), {})
    assert [(l.name, l.target, l.cardinality, l.on, l.join) for l in spec(model, "O_PLANT").links] == [
        ("materials", "O_MATERIAL", "many", (("id", "plant_id"),), "fk"),
    ]
    assert [(l.name, l.cardinality) for l in spec(model, "O_MATERIAL").links] == [("plant", "one")]

    # A second foreign key to the same table: each to-one is named by its
    # column; the to-many names clash, so the later one gets its column suffix.
    layer = capture().to_dict()
    record(layer, "O_MATERIAL")["attributes"].append(attribute("ORIGIN_ID", '"o_Material"."Origin_ID"'))
    tables = {**TABLES, "o_Material": {
        **TABLES["o_Material"], "columns": {**TABLES["o_Material"]["columns"], "Origin_ID": "STRING"}}}
    joins = [*JOINS, {"one": "o_Plant", "many": "o_Material", "columns": [["ID", "Origin_ID"]]}]
    model = normalize(rebuild(layer, joins=joins, tables=tables), {})
    assert {l.name for l in spec(model, "O_MATERIAL").links} == {"plant", "origin"}
    assert {l.name for l in spec(model, "O_PLANT").links} == {"materials", "materials_by_plant"}


def test_declared_links_rename_matching_automatic_links():
    mapping = {"objects": {"O_PLANT": {"links": {"inventory": {
        "target": "O_MATERIAL", "cardinality": "many", "on": {"ID": "PLANT_ID"}}}}}}
    model = normalize(capture(), mapping)
    assert [(l.name, l.join) for l in spec(model, "O_PLANT").links] == [("inventory", "fk")]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"key": ["COUNT"], "types": {"COUNT": "float"}}, "has type float"),
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


def test_declared_identifier_is_the_key_without_a_primary_key():
    tables = {**TABLES, "o_Plant": {**TABLES["o_Plant"], "primary_key": []}}
    model = normalize(rebuild(capture().to_dict(), tables=tables), {})
    assert spec(model, "O_PLANT").key == ("id",)

    layer = capture().to_dict()
    record(layer, "O_PLANT")["identifier"] = {"pql": '"o_Plant"."Other"'}
    model = normalize(rebuild(layer, tables=tables), {})
    assert "O_PLANT" not in {o.record_id for o in model.objects}
    assert "O_PLANT: no primary key or declared identifier; not an object type." in model.diagnostics


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
    with pytest.raises(ObjectMappingError, match="O_STOCK: no free class name among Plant"):
        normalize(capture(), mapping)
    mapping["objects"]["O_STOCK"]["class"] = "not a class"
    with pytest.raises(ObjectMappingError, match="capitalized Python identifier"):
        normalize(capture(), mapping)
    mapping = json.loads(json.dumps(MAPPING))
    mapping["exclude"] = ["O_STOCK"]
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
    module = load(write(tmp_path / "names", rebuild(layer)))
    names = [f.name for f in module.Plant.fields]
    assert {"key_attribute", "links_attribute", "date", "region"} <= set(names)
    assert {"country_attribute_1", "country_attribute_2"} <= set(names)
    assert module.Plant.fields["Country"].name != module.Plant.fields["COUNTRY"].name


def test_an_id_in_several_collections_loads_the_first():
    layer = capture().to_dict()
    record(layer, "O_PLANT")["newAttributes"] = [attribute("COUNTRY", '"o_Plant"."C2"')]
    changed = rebuild(layer)
    model = normalize(changed, MAPPING)
    countries = [f for f in spec(model, "O_PLANT").fields if f.attribute_id == "COUNTRY"]
    assert [(f.name, f.expression) for f in countries] == [("country", '"o_Plant"."Country"')]
    assert "O_PLANT.newAttributes.COUNTRY: ID also defined in attributes; not generated." in model.diagnostics
    mapping = json.loads(json.dumps(MAPPING))
    mapping["objects"]["O_PLANT"]["exclude-fields"] = ["COUNTRY"]
    plant = spec(normalize(changed, mapping), "O_PLANT")
    assert "COUNTRY" not in {f.attribute_id for f in plant.fields}
    ids = ["ID", "ID_ATTRIBUTE", "ID_ATTRIBUTE_1", "NumberName", "number_name", "KEY"]
    assert _names(ids, {"id", "key"}, suffixes=["attribute"] * 6) == [
        "id_attribute_2", "id_attribute", "id_attribute_1",
        "number_name_attribute_1", "number_name_attribute_2", "key_attribute",
    ]

def test_links_are_classified_against_data_model_joins(tmp_path):
    module = load(write(tmp_path / "joined"))
    Plant, Material = module.Plant, module.Material
    links = Plant.fields.links
    # Plant -> Material follows the captured foreign key in both directions.
    assert links["materials"].join == "fk"
    assert Material.fields.links["plant"].join == "fk"
    # Stock lines have no foreign key and the link is to-many: traversal only.
    assert links["stock"].join is None
    assert not hasattr(Plant.relations, "stock")
    assert hasattr(Plant.relations, "materials")
    definitions = generate(capture(), MAPPING)["definitions.py"].decode()
    assert "O_PLANT.links.stock: no Data Model foreign key or lookup path" in definitions
    assert Plant.fields._table == "o_Plant"


def test_to_one_links_without_foreign_keys_use_lookup(tmp_path):
    no_joins = rebuild(capture().to_dict(), joins=[])
    mapping = json.loads(json.dumps(MAPPING))
    mapping["objects"]["O_PLANT"]["links"]["materials"] = {
        "target": "O_MATERIAL", "cardinality": "many", "on": {"ID": "PLANT_ID"}}
    mapping["objects"]["O_MATERIAL"]["links"] = {
        "plant": {"target": "O_PLANT", "cardinality": "one", "on": {"PLANT_ID": "ID"}}}
    module = load(write(tmp_path / "unjoined", no_joins, mapping))
    assert module.Material.fields.links["plant"].join == "lookup"
    assert module.Plant.fields.links["materials"].join is None
    assert hasattr(module.Material.relations, "plant")
    assert not hasattr(module.Plant.relations, "materials")
