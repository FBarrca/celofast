"""Minimal command-line interface for capturing cloud Knowledge Models."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from celofast.sdk.capture import retrieve
from celofast.sdk.mapping import normalize
from celofast.sdk.package import write_package
from celofast.sdk.validation import resolve_types, validate


def _configuration(name: str, project: Path | None) -> tuple[dict[str, Any], Path]:
    if project is None:
        project = next(
            (
                parent / "pyproject.toml"
                for parent in (Path.cwd(), *Path.cwd().parents)
                if (parent / "pyproject.toml").is_file()
            ),
            None,
        )
    if project is None:
        raise ValueError(
            "No pyproject.toml found. Supply explicit KM arguments or --project."
        )
    project = project.resolve()
    with project.open("rb") as stream:
        config = tomllib.load(stream)
    models = config.get("tool", {}).get("celofast", {}).get("knowledge-models", {})
    if name not in models:
        raise ValueError(f"Knowledge Model {name!r} is not configured in {project}.")
    settings = models[name]
    if not isinstance(settings, dict):
        raise TypeError(f"Knowledge Model {name!r} configuration must be a table.")
    unexpected = set(settings) - {
        "space-id", "package-id", "key", "mode", "output", "mapping"
    }
    if unexpected:
        raise ValueError(
            f"Unknown KM configuration fields: {', '.join(sorted(unexpected))}"
        )
    return settings, project.parent


class _Progress:
    """Progress for slow pull steps: a Rich bar with ETA, or plain lines when redirected."""

    def __init__(self) -> None:
        from rich.console import Console

        self._console = Console(stderr=True)
        self._bar: Any = None
        self._task: Any = None
        self._title: str | None = None
        self._started = 0.0

    def __call__(self, task: str, completed: int, total: int) -> None:
        import time

        title = task.split(":", 1)[0]
        if not self._console.is_terminal:
            if title != self._title:
                self._title, self._started = title, time.monotonic()
            elapsed = time.monotonic() - self._started
            eta = elapsed / completed * (total - completed) if completed else 0.0
            suffix = f", ETA {eta:.0f}s" if 0 < completed < total else ""
            self._console.print(f"celofast: {task} ({completed}/{total}{suffix})", markup=False)
            return
        if title != self._title:
            self.close()
            from rich.progress import (
                BarColumn,
                MofNCompleteColumn,
                Progress,
                TextColumn,
                TimeElapsedColumn,
                TimeRemainingColumn,
            )

            self._bar = Progress(
                TextColumn("{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                console=self._console,
                transient=True,
            )
            self._task = self._bar.add_task(task, total=total)
            self._bar.start()
            self._title = title
        self._bar.update(self._task, completed=completed, total=total, description=task)

    def close(self) -> None:
        if self._bar is not None:
            self._bar.stop()
        self._bar = self._task = self._title = None


def _mapping(value: Any, base: Path) -> dict[str, Any] | None:
    """Read an inline mapping table or a TOML file relative to ``base``."""
    if value is None or isinstance(value, dict):
        return value
    if not isinstance(value, (str, Path)):
        raise TypeError("KM mapping must be a table or a path to a TOML file.")
    path = Path(value)
    with (path if path.is_absolute() else base / path).open("rb") as stream:
        return tomllib.load(stream)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="celofast",
        description="Generate typed Python object classes from Celonis Knowledge Models.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    km = commands.add_parser("km", help="Generate Knowledge Model SDKs")
    actions = km.add_subparsers(dest="action", required=True)
    pull = actions.add_parser(
        "pull", help="Capture a cloud KM and generate its Python package"
    )
    pull.add_argument("name", nargs="?", help="Configured Knowledge Model name")
    pull.add_argument("--project", type=Path, help="Path to pyproject.toml")
    pull.add_argument("--space-id")
    pull.add_argument("--package-id")
    pull.add_argument("--km", dest="key", help="Exact Knowledge Model key")
    pull.add_argument("--mode", choices=("draft", "published"))
    pull.add_argument("--output", type=Path)
    pull.add_argument(
        "--mapping",
        type=Path,
        help="Optional TOML file of overrides: exclusions, keys, types, and link names",
    )
    pull.add_argument(
        "--check",
        action="store_true",
        help="Report differences without writing (exit 1 for drift)",
    )
    args = parser.parse_args(argv)
    try:
        settings, root = (
            _configuration(args.name, args.project) if args.name else ({}, Path.cwd())
        )
        if args.project and not args.name:
            raise ValueError("--project requires a configured Knowledge Model name.")
        for key in ("space_id", "package_id", "key", "mode", "output"):
            override = getattr(args, key)
            if override is not None:
                settings[key.replace("_", "-")] = override
        settings.setdefault("mode", "draft")
        missing = [
            key
            for key in ("space-id", "package-id", "key", "output")
            if not settings.get(key)
        ]
        if missing:
            raise ValueError(f"Missing KM configuration: {', '.join(missing)}")
        if settings["mode"] not in ("draft", "published"):
            raise ValueError("KM mode must be 'draft' or 'published'.")
        for key in ("space-id", "package-id", "key"):
            if not isinstance(settings[key], str) or not settings[key].strip():
                raise ValueError(f"KM {key} must be a non-empty string.")
        mapping = (
            _mapping(args.mapping, Path.cwd())
            if args.mapping is not None
            else _mapping(settings.get("mapping"), root)
        )
        output = Path(settings["output"])
        # Explicit output paths are relative to the shell; configured paths
        # remain relative to their pyproject.toml even when invoked elsewhere.
        if not output.is_absolute():
            output = (Path.cwd() if args.output is not None else root) / output
        from celofast import CeloFast

        cf = CeloFast(
            space_id=settings["space-id"],
            package_id=settings["package-id"],
            mode=settings["mode"],
        )
        native = cf._resolver.knowledge_model(settings["key"])
        progress = _Progress()
        try:
            capture = retrieve(
                native,
                data_model=cf._resolver.data_model(native),
                space_id=settings["space-id"],
                package_id=settings["package-id"],
                mode=settings["mode"],
                progress=progress,
            )
            connection = cf._km_connection(settings["key"])
            capture = resolve_types(capture, connection._type_of, mapping=mapping, progress=progress)
            capture = validate(capture, connection._probe, mapping=mapping, progress=progress)
        finally:
            progress.close()
        changes = write_package(capture, output, mapping=mapping, check=args.check)
        for change in changes:
            print(change)
            if args.check and change.diff:
                print(change.diff, end="" if change.diff.endswith("\n") else "\n")
        if args.check:
            print(f"{capture.source.key}: {'out of date' if changes else 'up to date'}")
            return 1 if changes else 0
        print(
            f"{capture.source.key}: {'generated' if changes else 'up to date'} at {output.resolve()}"
        )
        model = normalize(capture, mapping)
        links = sum(len(spec.links) for spec in model.objects)
        print(
            f"{len(model.objects)} object types, {links} links; "
            f"{len(model.diagnostics)} items skipped (listed in definitions.py)."
        )
        return 0
    except (Exception, KeyboardInterrupt) as exc:  # noqa: BLE001 -- CLI error boundary
        # No traceback or credential-bearing HTTP response is printed by the
        # default CLI. Native exceptions remain available to library callers.
        message = (
            str(exc)
            if isinstance(exc, (ValueError, TypeError, OSError))
            else type(exc).__name__
        )
        print(f"celofast: {message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
