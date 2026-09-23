from pathlib import Path

import pytest

from celofast.sdk import Capture, CaptureError, Source
from celofast.sdk.package import write_package


def capture(pql='"Plant"."Number"'):
    return Capture.create(
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
                    "id": "Plant",
                    "identifier": {"pql": pql},
                    "attributes": [
                        {"id": "Number", "columnType": "string", "pql": pql}
                    ],
                }
            ]
        },
    )


def files(path):
    return {item.name: item.read_bytes() for item in path.iterdir() if item.is_file()}


def test_input_default_drift_and_reload(tmp_path, monkeypatch):
    import importlib
    import sys

    base = capture()

    def snapshot(value):
        return Capture.create(
            base.source,
            base.to_dict(),
            input_variables={
                "months": {"key": "months", "defaultValue": value},
            },
        )

    def fresh_import():
        for name in [n for n in sys.modules if n.split(".")[0] == "input_snapshot"]:
            del sys.modules[name]
        return importlib.import_module("input_snapshot")

    target = tmp_path / "input_snapshot"
    write_package(snapshot("3"), target)
    monkeypatch.syspath_prepend(str(tmp_path))
    module = fresh_import()
    try:
        old = module.km
        before = files(target)
        changes = write_package(snapshot("12"), target, check=True)
        assert any(
            c.path == "inventory-km.input_variables.months.defaultValue"
            and c.category == "definition"
            for c in changes
        )
        assert files(target) == before
        write_package(snapshot("12"), target)
        module = fresh_import()
        assert old.input_variables["months"]["defaultValue"] == "3"
        assert module.km.input_variables["months"]["defaultValue"] == "12"
        assert not write_package(snapshot("12"), target, check=True)
    finally:
        for name in [n for n in sys.modules if n.split(".")[0] == "input_snapshot"]:
            del sys.modules[name]


def test_check_never_writes_and_pull_is_repeatable(tmp_path):
    target = tmp_path / "new-parent" / "inventory"
    assert write_package(capture(), target, check=True)
    assert not target.parent.exists()
    assert write_package(capture(), target)
    before = files(target)
    assert not write_package(capture(), target)
    assert not write_package(capture(), target, check=True)
    changes = write_package(capture('"Plant"."Name"'), target, check=True)
    assert any(
        change.path == "inventory-km.records.Plant.attributes.Number.pql"
        for change in changes
    )
    assert files(target) == before
    assert write_package(capture('"Plant"."Name"'), target)
    assert files(target) != before


def test_import_failure_preserves_previous_package(tmp_path, monkeypatch):
    target = tmp_path / "inventory"
    write_package(capture(), target)
    before = files(target)

    def fail(_):
        raise CaptureError("invalid import")

    monkeypatch.setattr("celofast.sdk.package._verify_import", fail)
    with pytest.raises(CaptureError, match="invalid import"):
        write_package(capture("changed"), target)
    assert files(target) == before
    assert not list(tmp_path.glob(".celofast-km-*"))


def test_replacement_failure_rolls_back(tmp_path, monkeypatch):
    target = tmp_path / "inventory"
    write_package(capture(), target)
    before = files(target)
    import os

    replace = os.replace

    def fail_stage(source, destination):
        if Path(source).name.startswith(".celofast-km-stage-"):
            raise OSError("simulated installation failure")
        replace(source, destination)

    monkeypatch.setattr("celofast.sdk.package.os.replace", fail_stage)
    with pytest.raises(OSError, match="installation failure"):
        write_package(capture("changed"), target)
    assert files(target) == before
    assert not list(tmp_path.glob(".celofast-km-*"))


def test_unrelated_files_are_never_removed(tmp_path):
    target = tmp_path / "inventory"
    write_package(capture(), target)
    handwritten = target / "my_code.py"
    handwritten.write_text("important = True")
    with pytest.raises(CaptureError, match="unrelated"):
        write_package(capture("changed"), target)
    assert handwritten.read_text() == "important = True"


def test_manual_generated_edit_is_detected_and_repaired(tmp_path):
    target = tmp_path / "inventory"
    write_package(capture(), target)
    (target / "__init__.py").write_text("broken locally")
    assert any(
        change.path == "files/__init__.py"
        for change in write_package(capture(), target, check=True)
    )
    write_package(capture(), target)
    assert not write_package(capture(), target, check=True)


def test_check_reports_symbol_renames_and_field_categories(tmp_path):
    target = tmp_path / "inventory"
    original = capture()
    write_package(original, target)
    layer = original.to_dict()
    attributes = layer["records"][0]["attributes"]
    attributes[0].update(columnType="integer", pql="42", description="Updated docs")
    layer["records"][0]["identifier"]["pql"] = "42"
    # Both source IDs normalize to number, so the existing symbol must change.
    attributes.append({"id": "NUMBER", "columnType": "string", "pql": "'new'"})
    changes = write_package(Capture.create(original.source, layer), target, check=True)
    assert {change.category for change in changes} == {
        "symbols",
        "structure",
        "type",
        "definition",
        "metadata",
        "files",
    }
    assert any(
        "symbols/Plant.number -> Plant.number_attribute_" in change.path
        for change in changes
    )
    assert any(
        "[definition]" in str(change) and change.path.endswith(".pql")
        for change in changes
    )


def test_output_change_during_staging_is_preserved(tmp_path, monkeypatch):
    target = tmp_path / "inventory"
    write_package(capture(), target)
    from celofast.sdk.package import _verify_import

    def concurrent_edit(stage):
        _verify_import(stage)
        (target / "__init__.py").write_text("a concurrent edit")

    monkeypatch.setattr("celofast.sdk.package._verify_import", concurrent_edit)
    with pytest.raises(CaptureError, match="changed during pull"):
        write_package(capture("changed"), target)
    assert (target / "__init__.py").read_text() == "a concurrent edit"


@pytest.mark.parametrize("location", ["__init__.py", "__pycache__"])
def test_directory_disguised_as_generated_file_is_protected(tmp_path, location):
    target = tmp_path / "inventory"
    write_package(capture(), target)
    path = target / location
    if path.is_file():
        path.unlink()
    path.mkdir(exist_ok=True)
    kept = path / "handwritten.py"
    kept.write_text("keep this")
    with pytest.raises(CaptureError):
        write_package(capture("changed"), target)
    assert kept.read_text() == "keep this"


def test_metadata_only_categories_still_report_drift(tmp_path):
    target = tmp_path / "inventory"
    original = capture()
    layer = original.to_dict()
    layer["activities"] = [{"id": "Review", "description": "Before"}]
    write_package(Capture.create(original.source, layer), target)
    before = files(target)
    layer["activities"][0]["description"] = "After"
    changes = write_package(Capture.create(original.source, layer), target, check=True)
    assert any(change.path.endswith("activities.Review.description") for change in changes)
    assert files(target) == before


def test_mapping_changes_are_drift_and_invalid_mappings_write_nothing(tmp_path):
    from celofast.exceptions import ObjectMappingError

    target = tmp_path / "inventory"
    write_package(capture(), target)
    renamed = {"objects": {"Plant": {"class": "Site"}}}
    changes = write_package(capture(), target, mapping=renamed, check=True)
    assert any(change.path == "symbols/Plant -> Site" for change in changes)
    before = files(target)
    broken = capture().to_dict()
    del broken["records"][0]["identifier"]
    with pytest.raises(ObjectMappingError, match="no declared identifier"):
        write_package(Capture.create(capture().source, broken), target)
    assert files(target) == before


def test_packages_from_the_query_runtime_are_replaced_with_the_object_layout(tmp_path):
    target = tmp_path / "inventory"
    target.mkdir()
    (target / "__init__.py").write_text("from celofast.sdk.objects import KnowledgeModel")
    (target / "capture.json").write_text(capture().to_json())
    (target / "schema.json").write_text('{"managed_by": "celofast.km", "runtime_api": 5}')
    (target / "py.typed").write_text("")
    assert write_package(capture(), target)
    assert sorted(files(target)) == sorted(
        ["__init__.py", "capture.json", "definitions.py", "links.py", "objects.py", "py.typed", "schema.json"]
    )
