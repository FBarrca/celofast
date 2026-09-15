"""Review and install generated packages without risking unrelated project files."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from celofast.sdk.capture import Capture, CaptureError
from celofast.sdk.generate import generate

_FILES = frozenset({"__init__.py", "capture.json", "schema.json", "py.typed"})


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    return path.exists() and bool(
        getattr(path.lstat(), "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


@dataclass(frozen=True)
class Change:
    """One human-readable difference, addressed by source identity where possible."""

    kind: str
    path: str

    @property
    def category(self) -> str:
        if self.path.startswith("files/"):
            return "files"
        if self.path.startswith("symbols/"):
            return "symbols"
        field = self.path.rsplit(".", 1)[-1]
        if field in {"columnType", "type"}:
            return "type"
        if field in {"description", "displayName", "shortDisplayName", "documentation"}:
            return "metadata"
        if set(self.path.split(".")) & {
            "pql",
            "value",
            "parameters",
            "dependencies",
            "filters",
        }:
            return "definition"
        if self.kind in {"+", "-"} or self.path.endswith(" (order)"):
            return "structure"
        return "metadata"

    def __str__(self) -> str:
        return f"{self.kind} [{self.category}] {self.path}"


def _symbols(manifest: dict[str, Any]) -> dict[str, str]:
    """Index generated names by source path so collision-driven renames are visible."""
    entries = manifest.get("objects")
    if not isinstance(entries, list):
        return {}
    return {
        json.dumps(entry["path"]): entry["python"]
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("path"), list)
        and isinstance(entry.get("python"), str)
    }


def differences(before: Any, after: Any, path: str = "") -> tuple[Change, ...]:
    """Compare definitions, preserving meaningful array order and source IDs."""
    if type(before) is not type(after):
        return (Change("~", path),)
    if isinstance(before, dict):
        changes = []
        for key in sorted(before.keys() | after.keys()):
            child = f"{path}.{key}" if path else key
            if key not in before:
                changes.append(Change("+", child))
            elif key not in after:
                changes.append(Change("-", child))
            else:
                changes.extend(differences(before[key], after[key], child))
        return tuple(changes)
    if isinstance(before, list):

        def by_id(items: list[Any]) -> dict[str, Any] | None:
            if not all(
                isinstance(item, dict) and isinstance(item.get("id"), str)
                for item in items
            ):
                return None
            result = {item["id"]: item for item in items}
            return result if len(result) == len(items) else None

        old, new = by_id(before), by_id(after)
        if old is not None and new is not None:
            result = differences(old, new, path)
            # Preserve order differences for collections whose order has meaning.
            common = set(old) & set(new)
            if [key for key in old if key in common] != [
                key for key in new if key in common
            ]:
                result += (Change("~", f"{path} (order)"),)
            return result
        if len(before) != len(after):
            return (Change("~", path),)
        return tuple(
            change
            for i, (old_item, new_item) in enumerate(zip(before, after))
            for change in differences(old_item, new_item, f"{path}[{i}]")
        )
    return () if before == after else (Change("~", path),)


def _existing(output: Path) -> dict[str, bytes]:
    if _is_link(output):
        raise CaptureError(f"Generated output must not be a symbolic link: {output}")
    if not output.exists():
        return {}
    if not output.is_dir():
        raise CaptureError(f"Generated output is not a directory: {output}")
    entries = list(output.iterdir())
    if not entries:
        return {}
    if any(_is_link(entry) for entry in entries):
        raise CaptureError(f"Generated output contains symbolic links: {output}")
    unexpected = [
        entry.name
        for entry in entries
        if entry.name not in _FILES and entry.name != "__pycache__"
    ]
    if unexpected:
        raise CaptureError(
            f"Refusing to replace unrelated files in {output}: {', '.join(sorted(unexpected))}"
        )
    if any(entry.name in _FILES and not entry.is_file() for entry in entries):
        raise CaptureError(f"Expected generated files, found directories in {output}.")
    cache = output / "__pycache__"
    if cache.exists() and (
        not cache.is_dir()
        or any(
            _is_link(entry) or not entry.is_file() or entry.suffix != ".pyc"
            for entry in cache.iterdir()
        )
    ):
        raise CaptureError(f"Refusing to remove unrelated content in {cache}.")
    try:
        manifest = json.loads((output / "schema.json").read_text(encoding="utf-8"))
        if manifest.get("managed_by") != "celofast.km":
            raise ValueError("missing generator ownership marker")
    except (OSError, ValueError, AttributeError) as exc:
        raise CaptureError(
            f"{output} is not a managed Celofast KM package: {exc}"
        ) from exc
    return {
        name: (output / name).read_bytes()
        for name in _FILES
        if (output / name).is_file()
    }


def _remove_owned(directory: Path, parent: Path) -> None:
    # Only newly created staging/backup directories immediately below the
    # verified output parent are eligible for recursive cleanup.
    if _is_link(directory) or directory.resolve().parent != parent.resolve():
        raise CaptureError(f"Unsafe generated-package cleanup path: {directory}")
    if not directory.name.startswith(".celofast-km-"):
        raise CaptureError(f"Unrecognized generated-package cleanup path: {directory}")
    shutil.rmtree(directory)


def _verify_import(stage: Path) -> None:
    script = (
        "import importlib.util,sys; "
        "spec=importlib.util.spec_from_file_location('_celofast_generated_check',sys.argv[1]); "
        "module=importlib.util.module_from_spec(spec); "
        "sys.modules[spec.name]=module; spec.loader.exec_module(module)"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(stage / "__init__.py")],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise CaptureError(
            f"Generated package failed offline import validation:\n{result.stderr.strip()}"
        )


def write_package(
    capture: Capture, output: str | Path, *, check: bool = False
) -> tuple[Change, ...]:
    """Generate, review, and safely install; check performs no filesystem writes.

    Returns differences from the existing package. An empty tuple means output
    already matches. Failed staging or replacement preserves the previous package.
    """
    requested = Path(output).absolute()
    if _is_link(requested):
        raise CaptureError(f"Generated output must not be a symbolic link: {requested}")
    target = requested.resolve()
    if target == target.parent:
        raise CaptureError("A filesystem root cannot be a generated output directory.")
    expected = generate(capture)
    before = _existing(target)
    changed_files = tuple(
        Change("~" if name in before else "+", f"files/{name}")
        for name, data in sorted(expected.items())
        if before.get(name) != data
    )
    changes: tuple[Change, ...] = ()
    if "capture.json" in before:
        try:
            previous = Capture.model_validate_json(before["capture.json"])
        except ValueError:
            changes = (Change("~", "capture.json (invalid local capture)"),)
        else:
            if previous.source != capture.source:
                raise CaptureError(
                    "Output belongs to a different KM source; choose a separate output directory."
                )
            changes = differences(
                previous.to_dict(), capture.to_dict(), capture.source.key
            )
    changes += changed_files
    if "schema.json" in before:
        old_symbols = _symbols(json.loads(before["schema.json"]))
        new_symbols = _symbols(json.loads(expected["schema.json"]))
        for path in sorted(old_symbols.keys() | new_symbols.keys()):
            old, new = old_symbols.get(path), new_symbols.get(path)
            if old != new:
                changes += (
                    Change(
                        "+" if old is None else "-" if new is None else "~",
                        f"symbols/{old} -> {new}"
                        if old and new
                        else f"symbols/{old or new}",
                    ),
                )
    if check or not changes:
        return changes

    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".celofast-km-stage-", dir=target.parent))
    backup: Path | None = None
    try:
        for name, data in expected.items():
            (stage / name).write_bytes(data)
        _verify_import(stage)
        # Recheck immediately before replacing; don't remove files added while
        # staging. A competing generator process is detected by byte changes.
        if _existing(target) != before:
            raise CaptureError(
                "Generated output changed during pull; retry after the other writer finishes."
            )
        if target.exists():
            backup = Path(
                tempfile.mkdtemp(prefix=".celofast-km-backup-", dir=target.parent)
            )
            backup.rmdir()
            os.replace(target, backup)
        try:
            os.replace(stage, target)
        except BaseException:
            if backup is not None:
                os.replace(backup, target)
                backup = None
            raise
        if backup is not None:
            try:
                _remove_owned(backup, target.parent)
            except OSError:
                warnings.warn(
                    f"SDK installed; previous generation retained at {backup}.",
                    RuntimeWarning,
                    stacklevel=2,
                )
            backup = None
    finally:
        if stage.exists():
            _remove_owned(stage, target.parent)
        # A backup left after failed rollback is deliberately retained for
        # recovery. Never delete the only surviving copy of previous output.
    return changes
