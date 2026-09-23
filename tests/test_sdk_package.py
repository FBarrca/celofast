from pathlib import Path

import pytest

from celofast.exceptions import ObjectMappingError
from celofast.sdk import Capture, CaptureError, Source
from celofast.sdk.package import write_package

SOURCE = Source(
    tenant_id="tenant",
    space_id="space",
    package_id="package",
    key="inventory-km",
    mode="draft",
)
PACKAGE = ["__init__.py", "definitions.py", "links.py", "objects.py", "py.typed"]


def capture(pql='"Plant"."Number"', **extra):
    return Capture.create(
        SOURCE,
        {
            "records": [
                {
                    "id": "Plant",
                    "identifier": {"pql": pql},
                    "attributes": [
                        {"id": "Number", "columnType": "string", "pql": pql}
                    ],
                }
            ],
            **extra,
        },
    )


def files(path):
    return {item.name: item.read_bytes() for item in path.iterdir() if item.is_file()}


def test_package_contains_only_python(tmp_path):
    target = tmp_path / "inventory"
    write_package(capture(), target)
    assert sorted(files(target)) == PACKAGE


def test_check_never_writes_and_pull_is_repeatable(tmp_path):
    target = tmp_path / "new-parent" / "inventory"
    assert write_package(capture(), target, check=True)
    assert not target.parent.exists()
    assert write_package(capture(), target)
    before = files(target)
    assert not write_package(capture(), target)
    assert not write_package(capture(), target, check=True)
    changes = write_package(capture('"Plant"."Name"'), target, check=True)
    assert [str(change) for change in changes] == ["~ files/definitions.py"]
    # Drift is a readable diff of the generated code.
    (definitions,) = changes
    assert "-        expression='\"Plant\".\"Number\"'," in definitions.diff
    assert "+        expression='\"Plant\".\"Name\"'," in definitions.diff
    assert files(target) == before
    assert write_package(capture('"Plant"."Name"'), target)
    assert files(target) != before


def test_changes_outside_generated_types_are_not_drift(tmp_path):
    target = tmp_path / "inventory"
    write_package(capture(), target)
    changed = capture(
        kpis=[{"id": "Value", "pql": "SUM(1)"}],
        activities=[{"id": "Review", "description": "After"}],
    )
    assert not write_package(changed, target, check=True)


def test_renamed_symbols_show_in_the_diff(tmp_path):
    target = tmp_path / "inventory"
    write_package(capture(), target)
    changes = write_package(capture(), target, mapping={"objects": {"Plant": {"class": "Site"}}},
                            check=True)
    diff = "".join(change.diff for change in changes)
    assert "-class Plant(_o.Object):" in diff and "+class Site(_o.Object):" in diff


def test_reload_after_pull_uses_new_definitions(tmp_path, monkeypatch):
    import importlib
    import sys

    def fresh_import():
        for name in [n for n in sys.modules if n.split(".")[0] == "snapshot"]:
            del sys.modules[name]
        return importlib.import_module("snapshot")

    target = tmp_path / "snapshot"
    write_package(capture(), target)
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        old = fresh_import().Plant.fields.number
        write_package(capture('"Plant"."Name"'), target)
        new = fresh_import().Plant.fields.number
        assert old.expression == '"Plant"."Number"'
        assert new.expression == '"Plant"."Name"'
        assert old.model is not new.model
    finally:
        for name in [n for n in sys.modules if n.split(".")[0] == "snapshot"]:
            del sys.modules[name]


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


def test_directories_without_a_generation_stamp_are_not_replaced(tmp_path):
    target = tmp_path / "inventory"
    target.mkdir()
    (target / "__init__.py").write_text("# my own package\n")
    with pytest.raises(CaptureError, match="not a managed Celofast KM package"):
        write_package(capture(), target)
    assert (target / "__init__.py").read_text() == "# my own package\n"


def test_output_of_another_source_is_protected(tmp_path):
    target = tmp_path / "inventory"
    write_package(capture(), target)
    other = Capture.create(SOURCE.model_copy(update={"key": "other-km"}), capture().to_dict())
    with pytest.raises(CaptureError, match="different KM source"):
        write_package(other, target)


def test_manual_generated_edit_is_detected_and_repaired(tmp_path):
    target = tmp_path / "inventory"
    write_package(capture(), target)
    definitions = target / "definitions.py"
    definitions.write_text(definitions.read_text() + "\n# local edit\n")
    changes = write_package(capture(), target, check=True)
    assert [str(change) for change in changes] == ["~ files/definitions.py"]
    assert "-# local edit" in changes[0].diff
    write_package(capture(), target)
    assert not write_package(capture(), target, check=True)


def test_output_change_during_staging_is_preserved(tmp_path, monkeypatch):
    target = tmp_path / "inventory"
    write_package(capture(), target)
    from celofast.sdk.package import _verify_import

    def concurrent_edit(stage):
        _verify_import(stage)
        (target / "objects.py").write_text("a concurrent edit")

    monkeypatch.setattr("celofast.sdk.package._verify_import", concurrent_edit)
    with pytest.raises(CaptureError, match="changed during pull"):
        write_package(capture("changed"), target)
    assert (target / "objects.py").read_text() == "a concurrent edit"


@pytest.mark.parametrize("location", ["definitions.py", "__pycache__"])
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


def test_invalid_mappings_write_nothing(tmp_path):
    target = tmp_path / "inventory"
    write_package(capture(), target)
    before = files(target)
    broken = capture().to_dict()
    del broken["records"][0]["identifier"]
    with pytest.raises(ObjectMappingError, match="no declared identifier"):
        write_package(Capture.create(SOURCE, broken), target)
    assert files(target) == before


@pytest.mark.parametrize("runtime", [5, 6])
def test_packages_with_capture_sidecars_are_replaced(tmp_path, runtime):
    target = tmp_path / "inventory"
    target.mkdir()
    (target / "__init__.py").write_text("from celofast.sdk.objects import KnowledgeModel")
    (target / "capture.json").write_text(capture().to_json())
    (target / "schema.json").write_text(f'{{"managed_by": "celofast.km", "runtime_api": {runtime}}}')
    (target / "py.typed").write_text("")
    changes = write_package(capture(), target)
    assert {"- files/capture.json", "- files/schema.json"} <= {str(c) for c in changes}
    assert sorted(files(target)) == PACKAGE
