import pytest

from celofast.sdk import Capture, CaptureError, Source
from celofast.sdk.package import write_package

SOURCE = Source(
    tenant_id="tenant",
    space_id="space",
    package_id="package",
    key="inventory-km",
    mode="draft",
)
PACKAGE = ["__init__.py", "objects.py", "py.typed"]


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
    assert [str(change) for change in changes] == ["~ files/objects.py"]
    # Drift is a readable diff of the generated code.
    (objects,) = changes
    assert "-    number: _d.Field[str] = _d.Field('Number', '\"Plant\".\"Number\"', 'str')" in objects.diff
    assert "+    number: _d.Field[str] = _d.Field('Number', '\"Plant\".\"Name\"', 'str')" in objects.diff
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
    renamed = capture()
    renamed.definition["records"][0]["displayName"] = "Site"  # Names the class of a record without a table.
    changes = write_package(renamed, target, check=True)
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
        assert old.owner is not new.owner
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
    definitions = target / "objects.py"
    definitions.write_text(definitions.read_text() + "\n# local edit\n")
    changes = write_package(capture(), target, check=True)
    assert [str(change) for change in changes] == ["~ files/objects.py"]
    assert "-# local edit" in changes[0].diff
    write_package(capture(), target)
    assert not write_package(capture(), target, check=True)


def test_directory_disguised_as_generated_file_is_protected(tmp_path):
    target = tmp_path / "inventory"
    write_package(capture(), target)
    path = target / "objects.py"
    path.unlink()
    path.mkdir()
    kept = path / "handwritten.py"
    kept.write_text("keep this")
    with pytest.raises(CaptureError):
        write_package(capture("changed"), target)
    assert kept.read_text() == "keep this"


def test_foreign_files_block_replacement(tmp_path):
    # Anything the generator does not write, including sidecars from older
    # layouts, is left alone; delete the directory to regenerate it.
    target = tmp_path / "inventory"
    write_package(capture(), target)
    (target / "capture.json").write_text("{}")
    with pytest.raises(CaptureError, match="unrelated files.*capture.json"):
        write_package(capture("changed"), target)
    assert (target / "capture.json").read_text() == "{}"


def test_modules_of_an_earlier_layout_are_replaced(tmp_path):
    from celofast.sdk.generate import HEADER, stamp

    target = tmp_path / "inventory"
    target.mkdir()
    (target / "__init__.py").write_text(HEADER + f"__celofast__ = {stamp(capture())!r}\n")
    (target / "links.py").write_text(HEADER + "old = True\n")
    changes = write_package(capture(), target)
    assert "- files/links.py" in [str(change) for change in changes]
    assert sorted(files(target)) == PACKAGE
