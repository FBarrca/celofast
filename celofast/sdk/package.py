"""Review and install generated packages without touching unrelated files."""

from __future__ import annotations

import ast
import difflib
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from celofast.sdk.capture import Capture, CaptureError
from celofast.sdk.generate import HEADER, MARKER, PACKAGE_FILES, generate
from celofast.sdk.mapping import MappingInput


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
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == [MARKER]:
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                return None
            return value if isinstance(value, dict) else None
    return None


def _generated(path: Path) -> bool:
    """Written by this generator: a package file, or a module with its header."""
    if not path.is_file():
        return False
    if path.name in PACKAGE_FILES:
        return True
    with path.open("rb") as stream:
        return stream.readline().rstrip() == HEADER.rstrip().encode()


def _existing(output: Path, capture: Capture) -> dict[str, bytes]:
    """The current generated files; refuses directories this generator does not own."""
    if not output.exists():
        return {}
    if not output.is_dir():
        raise CaptureError(f"Generated output is not a directory: {output}")
    entries = [entry for entry in output.iterdir() if entry.name != "__pycache__"]
    if not entries:
        return {}
    unexpected = [entry.name for entry in entries if not _generated(entry)]
    if unexpected:
        raise CaptureError(
            f"Refusing to replace unrelated files in {output}: {', '.join(sorted(unexpected))}"
        )
    files = {entry.name: entry.read_bytes() for entry in entries}
    stamp = _stamp(files)
    if not stamp or stamp.get("managed_by") != "celofast.km":
        raise CaptureError(f"{output} is not a managed Celofast KM package: no generation stamp found.")
    if stamp.get("source") != capture.source.model_dump():
        raise CaptureError("Output belongs to a different KM source; choose a separate output directory.")
    return files


def differences(before: Mapping[str, bytes], after: Mapping[str, bytes]) -> tuple[Change, ...]:
    """File-level changes between two package contents, with code diffs."""
    changes = []
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name), after.get(name)
        if old == new:
            continue
        kind = "+" if old is None else "-" if new is None else "~"
        diff = "" if name == "py.typed" else "".join(difflib.unified_diff(
            (old or b"").decode("utf-8").splitlines(keepends=True),
            (new or b"").decode("utf-8").splitlines(keepends=True),
            f"a/{name}", f"b/{name}",
        ))
        changes.append(Change(kind, f"files/{name}", diff))
    return tuple(changes)


def _verify_import(files: Mapping[str, bytes]) -> None:
    """Import the package in a fresh interpreter before it replaces anything."""
    with tempfile.TemporaryDirectory(prefix="celofast-km-") as directory:
        for name, data in files.items():
            (Path(directory) / name).write_bytes(data)
        # Import as a package so the generated modules' relative imports resolve.
        script = (
            "import importlib.util,pathlib,sys; path=pathlib.Path(sys.argv[1]); "
            "spec=importlib.util.spec_from_file_location('_celofast_generated_check',"
            "path/'__init__.py',submodule_search_locations=[str(path)]); "
            "module=importlib.util.module_from_spec(spec); "
            "sys.modules[spec.name]=module; spec.loader.exec_module(module)"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", script, directory],
            capture_output=True, text=True, timeout=60, check=False,
        )
    if result.returncode:
        raise CaptureError(f"Generated package failed offline import validation:\n{result.stderr.strip()}")


def write_package(
    capture: Capture,
    output: str | Path,
    *,
    mapping: MappingInput = None,
    check: bool = False,
) -> tuple[Change, ...]:
    """Generate and install a package; ``check`` only reports what would change.

    ``mapping`` supplies object keys, types, exclusions, and relationships.
    Returns the changed files, each with a unified diff of generated code. An
    empty tuple means the output already matches: KM changes that do not affect
    the generated types are not drift.
    """
    target = Path(output).resolve()
    expected = generate(capture, mapping)
    changes = differences(_existing(target, capture), expected)
    if check or not changes:
        return changes
    _verify_import(expected)
    target.mkdir(parents=True, exist_ok=True)
    for name, data in expected.items():
        (target / name).write_bytes(data)
    for change in changes:
        if change.kind == "-":  # Modules of an earlier package layout.
            (target / change.path.removeprefix("files/")).unlink()
    return changes
