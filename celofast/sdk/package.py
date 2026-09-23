"""Review and install generated packages without risking unrelated project files."""

from __future__ import annotations

import ast
import difflib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from celofast.sdk.capture import Capture, CaptureError
from celofast.sdk.generate import MARKER, PACKAGE_FILES, generate
from celofast.sdk.mapping import MappingConfig

_FILES = frozenset(PACKAGE_FILES)


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    return path.exists() and bool(
        getattr(path.lstat(), "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


@dataclass(frozen=True)
class Change:
    """One changed file of the generated package, with a unified diff for code."""

    kind: str
    path: str
    diff: str = ""

    def __str__(self) -> str:
        return f"{self.kind} {self.path}"


def _stamp(files: Mapping[str, bytes]) -> dict[str, Any] | None:
    """Read the ``__celofast__`` ownership stamp from ``__init__.py``."""
    try:
        tree = ast.parse(files.get("__init__.py", b"").decode("utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and [getattr(t, "id", None) for t in node.targets] == [MARKER]
        ):
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                return None
            return value if isinstance(value, dict) else None
    return None


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
    files = {name: (output / name).read_bytes() for name in _FILES if (output / name).is_file()}
    stamp = _stamp(files)
    if not stamp or stamp.get("managed_by") != "celofast.km":
        raise CaptureError(
            f"{output} is not a managed Celofast KM package: no generation stamp found."
        )
    return files


def _diff(name: str, before: bytes | None, after: bytes | None) -> str:
    if name == "py.typed":
        return ""  # An empty marker: report the file, not its content.
    old = (before or b"").decode("utf-8").splitlines(keepends=True)
    new = (after or b"").decode("utf-8").splitlines(keepends=True)
    return "".join(difflib.unified_diff(old, new, f"a/{name}", f"b/{name}"))


def differences(before: Mapping[str, bytes], after: Mapping[str, bytes]) -> tuple[Change, ...]:
    """File-level changes between two package contents, with code diffs."""
    changes = []
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name), after.get(name)
        if old == new:
            continue
        kind = "+" if old is None else "-" if new is None else "~"
        changes.append(Change(kind, f"files/{name}", _diff(name, old, new)))
    return tuple(changes)


def _remove_owned(directory: Path, parent: Path) -> None:
    # Only newly created staging/backup directories immediately below the
    # verified output parent are eligible for recursive cleanup.
    if _is_link(directory) or directory.resolve().parent != parent.resolve():
        raise CaptureError(f"Unsafe generated-package cleanup path: {directory}")
    if not directory.name.startswith(".celofast-km-"):
        raise CaptureError(f"Unrecognized generated-package cleanup path: {directory}")
    shutil.rmtree(directory)


def _verify_import(stage: Path) -> None:
    # Import as a package so the generated modules' relative imports resolve.
    script = (
        "import importlib.util,pathlib,sys; "
        "path=pathlib.Path(sys.argv[1]); "
        "spec=importlib.util.spec_from_file_location('_celofast_generated_check',"
        "path/'__init__.py',submodule_search_locations=[str(path)]); "
        "module=importlib.util.module_from_spec(spec); "
        "sys.modules[spec.name]=module; spec.loader.exec_module(module)"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(stage)],
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
    capture: Capture,
    output: str | Path,
    *,
    mapping: Mapping[str, Any] | MappingConfig | None = None,
    check: bool = False,
) -> tuple[Change, ...]:
    """Generate, review, and safely install; check performs no filesystem writes.

    ``mapping`` supplies object keys, types, exclusions, and relationships.

    Returns the changed files, each with a unified diff of generated code. An
    empty tuple means the output already matches: KM changes that do not affect
    the generated types are not drift. Failed staging or replacement preserves
    the previous package.
    """
    requested = Path(output).absolute()
    if _is_link(requested):
        raise CaptureError(f"Generated output must not be a symbolic link: {requested}")
    target = requested.resolve()
    if target == target.parent:
        raise CaptureError("A filesystem root cannot be a generated output directory.")
    expected = generate(capture, mapping)
    before = _existing(target)
    if before:
        previous = (_stamp(before) or {}).get("source")
        if previous is not None and previous != capture.source.model_dump():
            raise CaptureError(
                "Output belongs to a different KM source; choose a separate output directory."
            )
    changes = differences(before, expected)
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
