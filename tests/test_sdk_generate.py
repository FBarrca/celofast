import ast
import dataclasses
import subprocess
import sys
from datetime import datetime

import pytest

from celofast.sdk import Field, ObjectModel
from celofast.sdk.generate import PACKAGE_FILES, generate
from celofast.sdk.model import _names, normalize

from celofast.sdk import Capture

from objects_fixture import INPUTS, JOINS, TABLES, attribute, capture, load, write


def record(layer, record_id):
    return next(item for item in layer["records"] if item["id"] == record_id)


def rebuild(layer, *, joins=JOINS, tables=TABLES):
    """A capture of a changed layer with the fixture's Data Model metadata."""
    return Capture(source=capture().source, definition=layer, input_variables=INPUTS, joins=joins, tables=tables)


def spec(model, record_id):
    return next(o for o in model.objects if o.record_id == record_id)


def test_package_layout_and_offline_import(tmp_path):
    files = generate(capture())
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
    Plant, Material, Stock = module.Plant, module.Material, module.Stock

    assert isinstance(module.km, ObjectModel)
    assert list(module.km) == [module.PlantActivity, Material, Plant, Stock]
    assert module.km["O_PLANT"] is Plant
    assert module.__all__ == ["PlantActivity", "Material", "Plant", "Stock", "km"]

    # Plant.fields describes the type; its members are typed Field definitions.
    definition = Plant.fields
    assert definition.object_type == "O_PLANT"
    assert isinstance(definition.country, Field)
    assert definition.country.id == "COUNTRY"
    assert definition["Description"] is definition.description
    assert [f.name for f in definition.key_fields] == ["id"]
    assert [f.name for f in definition] == ["id", "country", "plantnumber", "opened", "description"]
    assert Plant.relations.materials.target is Material
    assert definition.id.nullable is False and definition.country.nullable is True

    # Plant describes one loaded object: plain values plus key.
    names = [f.name for f in dataclasses.fields(Plant)]
    assert names == ["key", "id", "country", "plantnumber", "opened", "description"]
    plant = Plant(key="P1", id="P1", country="DE", plantnumber=None, opened=datetime(2020, 1, 1), description="x")
    assert plant.country == "DE" and plant.plantnumber is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        plant.country = "FR"
    assert plant == Plant(key="P1", id="P1", country="DE", plantnumber=None, opened=datetime(2020, 1, 1), description="x")
    assert dataclasses.asdict(plant) == {
        "key": "P1", "id": "P1", "country": "DE", "plantnumber": None,
        "opened": datetime(2020, 1, 1), "description": "x",
    }
    assert "_context" not in repr(plant)

    assert Stock.fields.object_type == "O_STOCK"
    assert [f.name for f in Stock.fields.key_fields] == ["plant_id", "day"]
    assert Material.fields.untyped.value_type == "str"


def test_generated_source_declares_explicit_types(tmp_path):
    files = generate(capture())
    objects = files["objects.py"].decode()
    tree = ast.parse(objects)
    stock = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Stock")
    annotations = {
        n.target.id: ast.unparse(n.annotation) for n in stock.body if isinstance(n, ast.AnnAssign)
    }
    # Celonis DATE columns hold timestamps: they load as datetimes.
    assert annotations["key"] == "tuple[str, _dt.datetime]"
    assert annotations["day"] == "_dt.datetime"
    assert annotations["plant_id"] == "str"
    assert annotations["qty"] == "int | None"
    assert annotations["fields"] == "ClassVar[StockDefinition]"
    assert "country: _d.Field[str | None] = _d.Field(" in objects
    assert "id: _d.Field[str] = _d.Field(" in objects
    assert "day: _d.DateTimeField[_dt.datetime] = _d.DateTimeField(" in objects
    assert "opened: _d.DateTimeField[_dt.datetime | None] = _d.DateTimeField(" in objects
    assert "plant = _o.ToOneRelation(Plant, on=(('plant_id', 'id'),))" in objects
    assert "materials = _o.ToManyRelation(Material, on=(('id', 'plant_id'),))" in objects


def test_package_is_self_contained_python(tmp_path):
    files = generate(capture())
    assert not [name for name in files if name.endswith(".json")]
    module = load(write(tmp_path / "inventory"))

    # Everything the runtime needs is written as literals in the code.
    assert module.km.source == capture().source
    assert module.km.data_model_id == "dm"
    assert module.km.variables == {"factor": "NUMBER"}  # Used by Material.stock's expression.
    country = module.Plant.fields.country
    assert (country.id, country.expression, country.value_type) == (
        "COUNTRY", '"o_Plant"."Country"', "str",
    )
    assert module.Plant.fields.metadata == {"displayName": "Plant", "description": None}
    assert module.Plant.fields.country.owner is type(module.Plant.fields)

    # The stamp identifies generated output and its source; nothing else.
    assert module.__celofast__ == {
        "managed_by": "celofast.km",
        "source": capture().source.model_dump(),
    }


def test_inputs_the_km_does_not_define_are_reported():
    layer = capture().definition
    record(layer, "O_PLANT")["attributes"][1]["pql"] = '"o_Plant"."Country" || ${missing}'
    model = normalize(rebuild(layer))
    assert "COUNTRY" not in {f.attribute_id for f in spec(model, "O_PLANT").fields}
    assert "O_PLANT.COUNTRY: uses ${missing}, which the KM does not define; not generated." in model.diagnostics


def test_variables_in_comments_are_not_reported(tmp_path):
    layer = capture().definition
    record(layer, "O_PLANT")["attributes"][1]["pql"] = '"o_Plant"."Country" -- was ${old}'
    module = load(write(tmp_path / "commented", rebuild(layer)))
    assert module.km.variables == {"factor": "NUMBER"}


def test_generation_is_deterministic():
    assert generate(capture()) == generate(capture())


def test_records_keys_and_types_are_derived_from_the_data_model():
    model = normalize(capture())
    assert [(o.record_id, o.class_name, o.key) for o in model.objects] == [
        ("EL_LOG", "PlantActivity", ("case", "event_id")),
        ("O_MATERIAL", "Material", ("id",)),
        ("O_PLANT", "Plant", ("id",)),
        ("O_STOCK", "Stock", ("plant_id", "day")),  # Class name from the table.
    ]
    types = {f.attribute_id: f.value_type for f in spec(model, "O_MATERIAL").fields}
    # Data Model column types win over the KM's declared (or missing) types.
    assert types == {
        "ID": "str", "PLANT_ID": "str", "ACTIVE": "bool", "UPDATED": "datetime",
        "COUNT": "int", "UNTYPED": "str", "STOCK": "float",
    }
    assert {f.attribute_id: f.value_type for f in spec(model, "O_PLANT").fields}["OPENED"] == "datetime"


def test_records_without_primary_key_are_skipped():
    tables = {**TABLES, "o_Stock": {**TABLES["o_Stock"], "primary_key": []}}
    model = normalize(rebuild(capture().definition, tables=tables))
    assert "O_STOCK" not in {o.record_id for o in model.objects}
    assert "O_STOCK: no primary key or declared identifier; not an object type." in model.diagnostics


def test_event_logs_are_the_history_of_their_lead_object():
    model = normalize(capture())
    log = spec(model, "EL_LOG")
    assert (log.class_name, log.table, log.lead, log.key) == (
        "PlantActivity", "el__PlantActivities", "o_Plant", ("case", "event_id"),
    )
    # Role fields have fixed names; KM column types apply (the log is not a
    # Data Model table), and the constant epoch column is not loaded.
    assert [(f.name, f.attribute_id, f.value_type) for f in log.fields] == [
        ("activity", "ACTIVITY", "str"),
        ("executed_by", "EXECUTEDBY", "str"),
        ("event_id", "ID", "str"),
        ("case", "LEAD_OBJECT_ID", "str"),
        ("timestamp", "TIMESTAMP", "datetime"),
    ]
    assert [(l.name, l.target, l.cardinality, l.on) for l in log.links] == [
        ("case", "O_PLANT", "one", (("case", "id"),)),
    ]
    assert ("activities", "EL_LOG", "many", (("id", "case"),)) in [
        (l.name, l.target, l.cardinality, l.on) for l in spec(model, "O_PLANT").links
    ]


def test_event_log_names_avoid_their_lead_and_role_fields():
    layer = capture().definition
    log = record(layer, "EL_LOG")
    log["pql"] = '"el_celonis_Plant"'
    for item in log["attributes"]:
        item["pql"] = item["pql"].replace("el__PlantActivities", "el_celonis_Plant")
    # A business attribute spelled like a role field keeps its own name.
    log["attributes"].append(attribute("Activity", '"el_celonis_Plant"."Activity"'))
    model = normalize(rebuild(layer))
    event = spec(model, "EL_LOG")
    assert event.class_name == "PlantEvent"
    assert "activity_attribute" in {f.name for f in event.fields}
    assert "events" in {l.name for l in spec(model, "O_PLANT").links}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda layer: layer.pop("eventLogsMetadata"), "EL_LOG: event log without a lead object in the KM"),
        (lambda layer: record(layer, "EL_LOG")["attributes"].pop(4), "EL_LOG: event log with no loaded timestamp"),
        (lambda layer: record(layer, "EL_LOG").pop("defaultActivityAttributeId"), "with no loaded activity"),
        (lambda layer: layer["records"].remove(record(layer, "O_PLANT")), "lead o_Plant is not a generated object"),
    ],
)
def test_event_logs_that_cannot_be_generated_are_reported(change, message):
    layer = capture().definition
    change(layer)
    model = normalize(rebuild(layer))
    assert "EL_LOG" not in {o.record_id for o in model.objects}
    assert any(message in note for note in model.diagnostics), model.diagnostics


def test_unknown_types_and_missing_expressions_are_skipped_and_reported():
    layer = capture().definition
    record(layer, "O_MATERIAL")["attributes"] += [
        attribute("CALC", 'CASE WHEN "o_Material"."Count" > 1 THEN 1 END', None),
        {"id": "EMPTY", "columnType": "STRING", "type": "ATTRIBUTE"},
    ]
    changed = rebuild(layer)
    model = normalize(changed)
    loaded = {f.attribute_id for f in spec(model, "O_MATERIAL").fields}
    assert not {"CALC", "EMPTY"} & loaded
    assert "O_MATERIAL.CALC: unknown type None; not generated." in model.diagnostics
    assert "O_MATERIAL.EMPTY: no expression; not generated." in model.diagnostics
    # The type Celonis reported at pull loads a calculated attribute the KM leaves untyped.
    typed = changed.model_copy(update={"types": {'CASE WHEN "o_Material"."Count" > 1 THEN 1 END': "int"}})
    model = normalize(typed)
    assert {f.attribute_id: f.value_type for f in spec(model, "O_MATERIAL").fields}["CALC"] == "int"


def test_attributes_rejected_at_pull_are_skipped_and_reported():
    rejected = capture().model_copy(update={"validation": {"O_MATERIAL": {"COUNT": "fails in Celonis: boom"}}})
    model = normalize(rejected)
    assert "COUNT" not in {f.attribute_id for f in spec(model, "O_MATERIAL").fields}
    assert "O_MATERIAL.COUNT: fails in Celonis: boom; not generated." in model.diagnostics


def test_automatic_links_follow_foreign_keys():
    model = normalize(capture())
    assert [(l.name, l.target, l.cardinality, l.on) for l in spec(model, "O_PLANT").links] == [
        ("activities", "EL_LOG", "many", (("id", "case"),)),
        ("materials", "O_MATERIAL", "many", (("id", "plant_id"),)),
    ]
    assert [(l.name, l.cardinality) for l in spec(model, "O_MATERIAL").links] == [("plant", "one")]

    # A second foreign key to the same table: each to-one is named by its
    # column; the to-many names clash, so the later one gets its column suffix.
    layer = capture().definition
    record(layer, "O_MATERIAL")["attributes"].append(attribute("ORIGIN_ID", '"o_Material"."Origin_ID"'))
    tables = {**TABLES, "o_Material": {
        **TABLES["o_Material"], "columns": {**TABLES["o_Material"]["columns"], "Origin_ID": "STRING"}}}
    joins = [*JOINS, {"one": "o_Plant", "many": "o_Material", "columns": [["ID", "Origin_ID"]]}]
    model = normalize(rebuild(layer, joins=joins, tables=tables))
    assert {l.name for l in spec(model, "O_MATERIAL").links} == {"plant", "origin"}
    assert {l.name for l in spec(model, "O_PLANT").links} == {"activities", "materials", "materials_by_plant"}


def test_declared_identifier_is_the_key_without_a_primary_key():
    tables = {**TABLES, "o_Plant": {**TABLES["o_Plant"], "primary_key": []}}
    model = normalize(rebuild(capture().definition, tables=tables))
    assert spec(model, "O_PLANT").key == ("id",)

    layer = capture().definition
    record(layer, "O_PLANT")["identifier"] = {"pql": '"o_Plant"."Other"'}
    model = normalize(rebuild(layer, tables=tables))
    assert "O_PLANT" not in {o.record_id for o in model.objects}
    assert "O_PLANT: no primary key or declared identifier; not an object type." in model.diagnostics


def test_reserved_and_colliding_names_get_readable_suffixes(tmp_path):
    layer = capture().definition
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
    layer = capture().definition
    record(layer, "O_PLANT")["newAttributes"] = [attribute("COUNTRY", '"o_Plant"."C2"')]
    changed = rebuild(layer)
    model = normalize(changed)
    countries = [f for f in spec(model, "O_PLANT").fields if f.attribute_id == "COUNTRY"]
    assert [(f.name, f.expression) for f in countries] == [("country", '"o_Plant"."Country"')]
    assert "O_PLANT.newAttributes.COUNTRY: ID also defined in attributes; not generated." in model.diagnostics
    ids = ["ID", "ID_ATTRIBUTE", "ID_ATTRIBUTE_1", "NumberName", "number_name", "KEY"]
    assert _names(ids, {"id", "key"}, suffixes=["attribute"] * 6) == [
        "id_attribute_2", "id_attribute", "id_attribute_1",
        "number_name_attribute_1", "number_name_attribute_2", "key_attribute",
    ]


def test_links_follow_data_model_joins(tmp_path):
    module = load(write(tmp_path / "joined"))
    Plant, Material = module.Plant, module.Material
    # Plant -> Material follows the captured foreign key in both directions.
    assert Plant.relations.materials.target is Material
    assert Material.relations.plant.target is Plant
    # Stock lines have no foreign key to plants: no link.
    assert not hasattr(Plant.relations, "stock")
    assert Plant.fields._table == "o_Plant"
