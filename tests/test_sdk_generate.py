import ast
import importlib.util
import json
import sys
from dataclasses import FrozenInstanceError, fields

import pytest

from celofast.sdk import Capture, Source
from celofast.sdk.generate import _names, generate
from celofast.sdk.objects import Attribute


def load_generated(capture, tmp_path):
    files = generate(capture)
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    spec = importlib.util.spec_from_file_location(
        "sdk_fixture", tmp_path / "__init__.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module.km, json.loads(files["schema.json"])


def test_readable_collision_names_preserve_natural_fields_and_order_independence():
    ids = ["ID", "ID_ATTRIBUTE", "ID_ATTRIBUTE_1", "NumberName", "number_name", "METADATA"]
    suffixes = ["attribute"] * len(ids)
    names = _names(ids, {"id", "metadata"}, suffixes=suffixes)
    assert names == [
        "id_attribute_2", "id_attribute", "id_attribute_1",
        "number_name_attribute_1", "number_name_attribute_2", "metadata_attribute",
    ]
    assert _names(ids[::-1], {"id", "metadata"}, suffixes=suffixes) == names[::-1]


def test_id_attribute_has_a_readable_name_and_keeps_record_identity(tmp_path):
    capture = Capture.create(
        Source(tenant_id="t", space_id="s", package_id="p", key="km", mode="draft"),
        {"records": [{"id": "Plant", "attributes": [
            {"id": "ID", "columnType": "STRING", "pql": '"Plant"."ID"'},
        ]}]},
    )
    root, manifest = load_generated(capture, tmp_path)
    plant = root.records.plant
    assert plant.id == "Plant"
    assert plant.id_attribute is plant["ID"]
    assert plant.id_attribute.pql == '"Plant"."ID"'
    assert manifest["objects"][-1]["python"] == "km.records.plant.id_attribute"


def test_generated_fields_retain_one_object_per_captured_path(tmp_path):
    capture = Capture.create(
        Source(tenant_id="t", space_id="s", package_id="p", key="km", mode="draft"),
        {
            "records": [{
                "id": "Plant",
                "attributes": [{"id": "Country", "columnType": "STRING"}],
                "newAttributes": [{"id": "Active", "columnType": "BOOLEAN"}],
                "augmentedAttributes": [{"id": "Count", "columnType": "INTEGER"}],
            }, {"id": "Empty"}],
            "kpis": [{"id": "Value", "columnType": "FLOAT"}],
            "filters": [{"id": "Active", "pql": "FILTER 1 = 1;"}],
        },
    )
    source = generate(capture)["__init__.py"].decode()
    classes = [node for node in ast.parse(source).body if isinstance(node, ast.ClassDef)]
    # The source-level API is a set of typed fields, with no generated accessors.
    assert classes
    assert all(not any(isinstance(node, ast.FunctionDef) for node in cls.body) for cls in classes)
    root, _ = load_generated(capture, tmp_path)
    plant = root.records.plant
    assert {field.name for field in fields(root.records)} == {"capture", "path", "plant", "empty"}
    assert {field.name for field in fields(plant)} == {"capture", "path", "country", "active", "count"}
    assert plant["Active"] is plant.active
    assert plant["Count"] is plant.count
    assert [attr.id for attr in plant] == ["Country", "Active", "Count"]
    assert not hasattr(plant, "attributes")
    assert not hasattr(plant, "new_attributes")
    assert not hasattr(plant, "augmented_attributes")
    assert plant["Country"] is plant.country
    assert next(iter(plant)) is plant.country
    assert root.records["Plant"] is plant

    from celofast.sdk.objects import KnowledgeObject, Namespace

    by_path = {}

    def visit(obj):
        if obj.path in by_path:
            assert obj is by_path[obj.path]
            return
        by_path[obj.path] = obj
        for field in fields(obj):
            child = getattr(obj, field.name)
            if isinstance(child, (KnowledgeObject, Namespace)):
                assert vars(obj)[field.name] is child
                assert getattr(obj, field.name) is child
                assert child.capture is root.capture
                with pytest.raises(FrozenInstanceError):
                    setattr(obj, field.name, child)
                visit(child)

    visit(root)
    assert len(by_path) == 11
    assert len(plant) == 3
    assert len(root.records.empty) == 0
    assert list(root.records.empty) == []
    assert not hasattr(root.records.empty, "attributes")


def test_reload_retains_stored_records_and_attributes(tmp_path, monkeypatch):
    source = Source(tenant_id="t", space_id="s", package_id="p", key="km", mode="draft")

    def snapshot(field, value):
        return Capture.create(source, {"records": [{
            "id": "Plant",
            "attributes": [{"id": field, "columnType": "STRING", "pql": value}],
        }]})

    name = "sdk_stored_fields_fixture"
    package = tmp_path / name
    package.mkdir()
    monkeypatch.syspath_prepend(str(tmp_path))
    for filename, data in generate(snapshot("Country", "'DE'")).items():
        (package / filename).write_bytes(data)
    module = importlib.import_module(name)
    try:
        old = module.km
        old_records = old.records
        old_plant = old_records.plant
        old_country = old_plant.country
        for filename, data in generate(snapshot("Name", "'New plant'")).items():
            (package / filename).write_bytes(data)
        importlib.invalidate_caches()
        new = importlib.reload(module).km
        assert new.records.plant.name.pql == "'New plant'"
        assert not hasattr(new.records.plant, "country")
        assert old.records is old_records
        assert old.records.plant is old_plant
        assert old_plant.country is old_country
        assert old_plant["Country"] is old_country
        assert old_country.pql == "'DE'"
        assert not hasattr(old_plant, "name")
    finally:
        sys.modules.pop(name, None)


def test_module_reload_preserves_old_hierarchy_after_definition_removal(
    tmp_path, monkeypatch
):
    source = Source(tenant_id="t", space_id="s", package_id="p", key="km", mode="draft")
    before = Capture.create(
        source,
        {
            "kpis": [
                {
                    "id": "Value",
                    "pql": "41",
                    "columnType": "INTEGER",
                    "parameters": [{"id": "OldParameter"}],
                },
                {"id": "Removed", "pql": "1", "columnType": "INTEGER"},
            ]
        },
    )
    after = Capture.create(
        source,
        {
            "kpis": [
                {"id": "Value", "pql": "99", "columnType": "INTEGER", "parameters": []},
            ]
        },
    )
    name = "sdk_reload_fixture"
    package = tmp_path / name
    package.mkdir()
    monkeypatch.syspath_prepend(str(tmp_path))
    for filename, data in generate(before).items():
        (package / filename).write_bytes(data)
    module = importlib.import_module(name)
    try:
        old = module.km
        old_namespace = old.kpis
        for filename, data in generate(after).items():
            (package / filename).write_bytes(data)
        importlib.invalidate_caches()
        new = importlib.reload(module).km
        assert new.kpis.value.pql == "99"
        assert new.kpis.value.metadata["parameters"] == ()
        with pytest.raises(KeyError):
            new.kpis["Removed"]
        for namespace in (old_namespace, old.kpis):
            assert namespace.value.pql == "41"
            assert namespace.value.metadata["parameters"][0]["id"] == "OldParameter"
            assert namespace.removed.pql == "1"
    finally:
        sys.modules.pop(name, None)


@pytest.mark.parametrize("mode", ["draft", "published"])
def test_every_source_id_and_metadata_survives_unknown_nested_content(tmp_path, mode):
    source = Source(tenant_id="t", space_id="s", package_id="p", key="km", mode=mode)
    content = {
        "id": "root",
        "metadata": {"key": "km", "version": "1"},
        "records": [
            {
                "id": "Plant",
                "origin": "INHERITED",
                "autoGenerated": True,
                "identifier": {"id": "Identifier", "pql": '"Plant"."ID"'},
                "attributes": [
                    {
                        "id": "Number",
                        "columnType": "STRING",
                        "pql": "'one'",
                        "validationStatusType": "OPEN",
                        "validationStatus": None,
                    }
                ],
                "newAttributes": [{"id": "New", "columnType": "FLOAT"}],
                "augmentedAttributes": [{"id": "Augmented", "columnType": "DATE"}],
            }
        ],
        "kpis": [
            {
                "id": "Value",
                "parameters": [{"id": "P", "defaultValue": "2"}],
                "targets": [{"id": "T", "value": 10}],
                "breakdowns": [{"id": "B"}],
            }
        ],
        "futureCategory": [
            [{"id": "deep", "unknown": {"ordered": [3, 1], "null": None}}]
        ],
        "customObjects": [
            {"description": "An object without an ID", "payload": {"plain": True}}
        ],
    }
    for category in (
        "filters",
        "variables",
        "activities",
        "actions",
        "anomalies",
        "eventLogs",
        "ruleGroups",
        "visualMappings",
    ):
        content[category] = [
            {"id": category + "_item", "newMetadata": {"preserve": True}}
        ]
    capture = Capture.create(source, content)
    root, manifest = load_generated(capture, tmp_path)

    assert root.capture.to_dict() == capture.to_dict()
    assert root.metadata["futureCategory"][0][0]["id"] == "deep"
    assert root.metadata["customObjects"][0]["payload"]["plain"] is True
    assert root.records.plant.metadata["identifier"]["id"] == "Identifier"
    assert root.kpis.value.metadata["parameters"][0]["id"] == "P"
    assert not hasattr(root.kpis.value, "parameters")
    for category in ("variables", "activities", "actions", "future_category", "custom_objects"):
        assert not hasattr(root, category)
    assert {tuple(entry["path"]) for entry in manifest["objects"]} == {
        (), ("records", "Plant"),
        ("records", "Plant", "attributes", "Number"),
        ("records", "Plant", "newAttributes", "New"),
        ("records", "Plant", "augmentedAttributes", "Augmented"),
        ("kpis", "Value"), ("filters", "filters_item"),
    }


def test_names_cannot_shadow_runtime_and_collisions_remain_discoverable(tmp_path):
    source = Source(tenant_id="t", space_id="s", package_id="p", key="km", mode="draft")
    ids = [
        "NumberName",
        "number_name",
        "class",
        "1first",
        "日本",
        "metadata",
        "capture",
        "path",
        "_members",
    ]
    capture = Capture.create(
        source,
        {
            "namespace": [{"id": "Entry", "children": [{"id": "Nested"}]}],
            "record": {"id": "Plain", "children": [{"id": "Nested"}]},
            "records": [
                {
                    "id": "Plant",
                    "attributes": [
                        {"id": id_, "columnType": "STRING", "pql": "'value'"}
                        for id_ in ids
                    ],
                }
            ],
        },
    )
    root, manifest = load_generated(capture, tmp_path)
    assert {item.id for item in root.records.plant} == set(ids)
    assert root.records.plant["class"].id == "class"
    assert root.records.plant["metadata"].pql == "'value'"
    assert not hasattr(root, "namespace")
    assert root.metadata["namespace"][0]["children"][0]["id"] == "Nested"
    mappings = [entry["python"] for entry in manifest["objects"]]
    assert len(mappings) == len(set(mappings))


def test_generated_package_imports_offline_with_complete_discoverable_objects(tmp_path):
    capture = Capture.create(
        Source(
            tenant_id="tenant",
            space_id="space",
            package_id="package",
            key="inventory-km",
            mode="draft",
        ),
        {
            "records": [
                {
                    "id": "O_CELONIS_PLANT",
                    "type": "RECORD",
                    "attributes": [
                        {
                            "id": "NumberNameConcat",
                            "columnType": "string",
                            "pql": '\n"Plant"."Number" || \' - \' || "Plant"."Name"',
                            "description": 'Quotes """ and Unicode café',
                            "unknown": {"enabled": True},
                        },
                        {
                            "id": "NumberFormatted",
                            "columnType": "string",
                            "pql": '"Plant"."Number"',
                        },
                    ],
                }
            ],
            "futureObjects": [{"id": "class", "definition": {"preserved": [3, 1]}}],
        },
    )
    files = generate(capture)
    assert files == generate(capture)
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    spec = importlib.util.spec_from_file_location(
        "generated_inventory", tmp_path / "__init__.py"
    )
    module = importlib.util.module_from_spec(spec)
    # dataclasses use the module registry to resolve postponed annotations.
    import sys

    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        km = module.km
        from typing import get_type_hints

        assert get_type_hints(module)["km"] is type(km)
        plant = km.records.o_celonis_plant
        attr = plant.number_name_concat
        assert plant.number_name_concat == attr
        assert isinstance(attr, Attribute)
        assert attr.id == "NumberNameConcat"
        assert attr.column_type == "string"
        assert attr.pql.startswith('\n"Plant"')
        assert attr.metadata["unknown"]["enabled"] is True
        assert plant["NumberNameConcat"] == attr
        assert len(list(plant)) == 2
        assert not hasattr(km, "future_objects")
        assert km.metadata["futureObjects"][0]["id"] == "class"
        for obj in (km, plant, attr, km.records):
            with pytest.raises(FrozenInstanceError):
                obj.unexpected_mutation = 1
        assert not any(
            entry["id"] == "class"
            for entry in json.loads(files["schema.json"])["objects"]
        )
    finally:
        sys.modules.pop(spec.name, None)


def test_flat_fields_disambiguate_collisions_and_preserve_metadata(tmp_path):
    ids = ["Number", "metadata", "attributes", "NumberName", "number_name", "Shared", "get_attribute"]
    capture = Capture.create(
        Source(tenant_id="t", space_id="s", package_id="p", key="km", mode="draft"),
        {"records": [{
            "id": "Plant",
            "attributes": [
                {"id": id_, "columnType": "STRING", "pql": "'value'"}
                for id_ in ids
            ] + [{"id": "Nested", "columnType": "STRING", "pql": "'nested'",
                  "parameters": [{"id": "Parameter"}]}],
            "newAttributes": [{"id": "Shared", "columnType": "STRING", "pql": "'new'"}],
            "augmentedAttributes": [{"id": "Extra", "columnType": "INTEGER", "pql": "1"}],
        }]},
    )
    root, manifest = load_generated(capture, tmp_path)
    plant = root.records.plant
    assert plant.number is plant["Number"]
    assert plant.extra is plant["Extra"]
    assert plant.metadata["id"] == "Plant"
    assert plant["metadata"].pql == "'value'"
    assert plant["attributes"].pql == "'value'"
    assert plant["get_attribute"].pql == "'value'"
    assert callable(plant.get_attribute)
    assert not hasattr(plant, "number_name")
    assert not hasattr(plant, "shared")
    with pytest.raises(KeyError):
        plant["Shared"]
    assert plant.get_attribute("Shared", collection="attributes").pql == "'value'"
    assert plant.get_attribute("Shared", collection="newAttributes").pql == "'new'"
    assert plant.shared_attribute is plant.get_attribute("Shared", collection="attributes")
    assert plant.shared_new_attribute is plant.get_attribute("Shared", collection="newAttributes")
    assert plant.get_attribute("Extra", collection="augmentedAttributes") is plant.extra
    with pytest.raises(KeyError):
        plant.get_attribute("Shared", collection="unknown")
    with pytest.raises(KeyError):
        plant["missing"]
    assert plant.nested.metadata["parameters"][0]["id"] == "Parameter"
    # Every collision still has a typed, stored direct field advertised by the manifest.
    for entry in manifest["objects"]:
        if entry["class"].startswith("Attribute["):
            collection = entry["path"][-2]
            field_name = entry["python"].removeprefix("km.records.plant.")
            assert "." not in field_name
            assert vars(plant)[field_name] is plant.get_attribute(entry["id"], collection=collection)


def test_flattened_collision_names_are_stable_when_other_fields_are_inserted():
    source = Source(tenant_id="t", space_id="s", package_id="p", key="km", mode="draft")
    definition = {"records": [{
        "id": "Plant",
        "attributes": [{"id": "Shared", "columnType": "STRING"}],
        "newAttributes": [{"id": "Shared", "columnType": "INTEGER"}],
    }]}

    def symbols():
        manifest = json.loads(generate(Capture.create(source, definition))["schema.json"])
        return {tuple(entry["path"]): entry["python"] for entry in manifest["objects"] if entry["id"] == "Shared"}

    before = symbols()
    definition["records"][0]["attributes"].insert(0, {"id": "Inserted"})
    assert symbols() == before


def test_flat_records_preserve_anonymous_attributes_and_skip_unsupported_entries(tmp_path):
    capture = Capture.create(
        Source(tenant_id="t", space_id="s", package_id="p", key="km", mode="draft"),
        {"records": [{
            "id": "Plant",
            "attributes": [None, {"pql": "1"}, {"id": "Wrong", "type": "KPI"}],
            "newAttributes": [{"pql": "2"}, {"id": "Date", "columnType": "DATE"}],
        }]},
    )
    root, _ = load_generated(capture, tmp_path)
    plant = root.records.plant
    assert len(plant) == 3
    assert [attr.id for attr in plant] == [None, None, "Date"]
    assert [attr.path[-2:] for attr in plant] == [("attributes", 1), ("newAttributes", 0), ("newAttributes", "Date")]
    assert list(plant)[0] is plant.item_1
    assert list(plant)[1] is plant.item_0
    assert plant["Date"] is plant.date
    with pytest.raises(KeyError):
        plant["Wrong"]


def test_import_and_field_access_do_not_load_query_stack(tmp_path):
    import subprocess

    capture = Capture.create(
        Source(tenant_id="t", space_id="s", package_id="p", key="km", mode="draft"),
        {"records": [{"id": "Plant", "attributes": [
            {"id": "Number", "columnType": "STRING", "pql": "'123'"}
        ]}]},
    )
    package = tmp_path / "offline_inventory"
    package.mkdir()
    for name, data in generate(capture).items():
        (package / name).write_bytes(data)
    script = """
import sys
sys.path.insert(0, sys.argv[1])
class BlockQueryImports:
    def find_spec(self, fullname, path, target=None):
        if fullname.split('.')[0] in {'pycelonis', 'saolapy', 'pandas'}:
            raise AssertionError(f'Offline import loaded {fullname}')
sys.meta_path.insert(0, BlockQueryImports())
from offline_inventory import km
assert km.records.plant.number.pql == "'123'"
assert km.records.plant.number.desc().ascending is False
assert km.records.plant.number.eq("123").pql.endswith("= '123';")
assert 'celofast.builder' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
