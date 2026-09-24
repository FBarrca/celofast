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
    return Capture(source=SOURCE, definition={
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
        })


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
    other = Capture(source=SOURCE.model_copy(update={"key": "other-km"}), definition=capture().definition)
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


def test_directory_disguised_as_generated_file_is_protected(tmp_path):
    target = tmp_path / "inventory"
    write_package(capture(), target)
    path = target / "definitions.py"
    path.unlink()
    path.mkdir()
    kept = path / "handwritten.py"
    kept.write_text("keep this")
    with pytest.raises(CaptureError):
        write_package(capture("changed"), target)
    assert kept.read_text() == "keep this"


def test_invalid_mappings_write_nothing(tmp_path):
    target = tmp_path / "inventory"
    write_package(capture(), target)
    before = files(target)
    first = capture().definition["records"][0]["id"]
    with pytest.raises(ObjectMappingError, match="not a loaded field"):
        write_package(capture(), target, mapping={"objects": {first: {"key": ["MISSING"]}}})
    assert files(target) == before


def test_foreign_files_block_replacement(tmp_path):
    # Anything the generator does not write, including sidecars from older
    # layouts, is left alone; delete the directory to regenerate it.
    target = tmp_path / "inventory"
    write_package(capture(), target)
    (target / "capture.json").write_text("{}")
    with pytest.raises(CaptureError, match="unrelated files.*capture.json"):
        write_package(capture("changed"), target)
    assert (target / "capture.json").read_text() == "{}"
