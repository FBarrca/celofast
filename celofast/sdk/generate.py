"""Deterministic explicit Python declarations from a complete KM capture."""

from __future__ import annotations

import json
import keyword
import re
from typing import Any

from celofast.sdk.capture import Capture
from celofast.sdk.loading import RUNTIME_API_VERSION, capture_digest
from celofast.sdk.objects import Attribute, KnowledgeModel, KnowledgeObject, Namespace, Record

GENERATOR_VERSION = 7


def python_name(value: str) -> str:
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^a-zA-Z0-9_]", "_", value).lower().strip("_") or "item"
    if value[0].isdigit():
        value = "item_" + value
    if keyword.iskeyword(value):
        value += "_"
    return value


def _names(
    values: list[str], reserved: set[str], *, suffixes: list[str]
) -> list[str]:
    """Keep natural names; resolve collisions with kind names and small numbers."""
    names = [python_name(value) for value in values]
    result = [""] * len(names)
    occupied = set(reserved)
    pending = []
    for index, name in enumerate(names):
        if names.count(name) == 1 and name not in reserved:
            result[index] = name
            occupied.add(name)
        else:
            pending.append(index)
    candidates = {index: f"{names[index].rstrip('_')}_{suffixes[index]}" for index in pending}
    # Reserve each unique candidate before adding numbers, so a generated name
    # never steals another field's natural name. Sorting avoids order-based renames.
    occupied.update(candidates.values())
    for index in sorted(pending, key=lambda i: (values[i], suffixes[i])):
        candidate = candidates[index]
        if list(candidates.values()).count(candidate) == 1 and candidate not in reserved and candidate not in result:
            name = candidate
        else:
            number = 1
            name = f"{candidate}_{number}"
            while name in occupied:
                number += 1
                name = f"{candidate}_{number}"
        result[index] = name
        occupied.add(name)
    return result


def generate(capture: Capture) -> dict[str, bytes]:
    """Render a self-contained typed package without touching the filesystem."""
    declarations: list[str] = []
    initialization: list[str] = []
    inventory: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    object_names: dict[tuple[str | int, ...], str] = {}
    local_names: set[str] = set()
    class_names: dict[str, tuple[str | int, ...] | None] = dict.fromkeys(
        {
            "KnowledgeModel",
            "Record",
            "Attribute",
            "KPI",
            "Filter",
            "Namespace",
            "Path",
            "Any",
            "CapturedKnowledgeModel",
            "Capture",
        }
    )
    reserved = (
        set(dir(KnowledgeObject))
        | set(dir(KnowledgeModel))
        | set(dir(Attribute))
        | set(dir(Namespace))
        | set(dir(Record))
        | {"capture", "path"}
    )

    def class_name(path: tuple[str | int, ...]) -> str:
        if not path:
            return "CapturedKnowledgeModel"
        name = "".join(
            part[:1].upper() + part[1:]
            for segment in path
            for part in python_name(str(segment)).split("_")
            if part
        )
        base_name = name
        number = 2
        while name in class_names and class_names[name] != path:
            name = f"{base_name}{number}"
            number += 1
        class_names[name] = path
        return name

    def base_for(value: dict[str, Any], path: tuple[str | int, ...]) -> str:
        if not path:
            return "KnowledgeModel"
        collection = path[-2]
        base = {
            "records": "Record", "attributes": "Attribute",
            "newAttributes": "Attribute", "augmentedAttributes": "Attribute",
            "kpis": "KPI", "filters": "Filter",
        }[collection]
        if base in {"Attribute", "KPI"}:
            # Uppercase families verified against a live final-layer response.
            # These describe declared values, not pandas dtypes or nullability.
            column_type = value.get("columnType")
            type_ = {
                "string": "str",
                "boolean": "bool",
                "integer": "int",
                "float": "float",
                "date": "date",
                "datetime": "datetime",
            }.get(column_type.lower() if isinstance(column_type, str) else "", "Any")
            if type_ == "Any":
                diagnostics.append(
                    f"{path!r}: unknown value type {value.get('columnType')!r}; using Any"
                )
            return f"{base}[{type_}]"
        return base

    def construct(
        type_: str,
        path: tuple[str | int, ...],
        access: str,
        children: list[tuple[str, str]],
    ) -> None:
        # Keep temporary bindings local to the builder. The completed graph
        # retains its children without depending on mutable module globals.
        variable = "_" + access.replace(".", "_")
        while variable in local_names:
            variable += "_"
        local_names.add(variable)
        object_names[path] = variable
        initialization.extend(
            [
                f"    {variable} = {type_}(",
                "        capture=capture,",
                f"        path={path!r},",
                *(f"        {symbol}={child}," for symbol, child in children),
                "    )",
            ]
        )

    def entries_for(
        values: list[Any], path: tuple[str | int, ...], expected_type: str
    ) -> list[tuple[tuple[str | int, ...], dict[str, Any]]]:
        entries = [
            (index, item) for index, item in enumerate(values)
            if isinstance(item, dict) and item.get("type") in (None, expected_type)
        ]
        result = []
        for index, item in entries:
            source_id = item.get("id")
            segment = (
                source_id if isinstance(source_id, str)
                and sum(child.get("id") == source_id for _, child in entries) == 1
                else index
            )
            result.append(((*path, segment), item))
        return result

    def emit(value: Any, path: tuple[str | int, ...], access: str) -> str:
        name = class_name(path)
        fields: list[str] = []
        bindings: list[tuple[str, str]] = []
        entries: list[tuple[tuple[str | int, ...], dict[str, Any]]] = []
        if isinstance(value, dict):
            base = base_for(value, path)
            inventory.append(
                {
                    "path": list(path),
                    "id": value.get("id"),
                    "python": access,
                    "class": base,
                }
            )
            if base not in {"KnowledgeModel", "Record"}:
                construct(base, path, access, [])
                return base
            description = value.get("description") or value.get("displayName") or value.get("id")
            if description:
                fields.extend([f"    {str(description)!r}", ""])
            if base == "Record":
                # Flatten all source collections before resolving names, so
                # collisions cannot hide attributes from another collection.
                for collection in ("attributes", "newAttributes", "augmentedAttributes"):
                    entries.extend(entries_for(
                        value.get(collection) or [], (*path, collection), "ATTRIBUTE"
                    ))
            else:
                for symbol in ("records", "kpis", "filters"):
                    child_path = (*path, symbol)
                    child_class = emit(value.get(symbol) or [], child_path, f"{access}.{symbol}")
                    fields.append(f"    {symbol}: {child_class}")
                    bindings.append((symbol, object_names[child_path]))
        else:
            base = "Namespace"
            expected_type = {"records": "RECORD", "kpis": "KPI", "filters": "FILTER"}[path[-1]]
            entries = entries_for(value, path, expected_type)
            if not entries:
                construct("Namespace", path, access, [])
                return "Namespace"

        if base in {"Record", "Namespace"}:
            symbols = _names(
                [str(child.get("id") or f"item_{child_path[-1]}") for child_path, child in entries],
                reserved,
                suffixes=[{
                    "records": "record", "kpis": "kpi", "filters": "filter",
                    "attributes": "attribute", "newAttributes": "new_attribute",
                    "augmentedAttributes": "augmented_attribute",
                }[child_path[-2]] for child_path, _ in entries],
            )
            members = []
            for (child_path, child), symbol in zip(entries, symbols):
                child_class = emit(child, child_path, f"{access}.{symbol}")
                source_id = child.get("id")
                members.append((source_id, symbol))
                description = child.get("description") or child.get("displayName") or source_id or symbol
                fields.extend([
                    f"    {symbol}: {child_class}",
                    f"    {str(description)!r}",
                    "",
                ])
                bindings.append((symbol, object_names[child_path]))
            fields.extend([f"    _members = {tuple(members)!r}", ""])
        declarations.append(
            # Keyword-only children can follow KnowledgeObject.path's default.
            f"@dataclass(frozen=True, kw_only=True)\nclass {name}({base}):\n"
            + ("\n".join(fields) or "    pass\n")
        )
        construct(name, path, access, bindings)
        return name

    root_symbol = "km"
    emit(capture.to_dict(), (), root_symbol)
    header = (
        "# Generated by celofast km pull. Do not edit.\n"
        "from __future__ import annotations\n"
        "from pathlib import Path\n"
        "from dataclasses import dataclass\n"
        "from datetime import date, datetime\n"
        "from typing import Any\n"
        "from celofast.sdk.capture import Capture\n"
        "from celofast.sdk.loading import load_capture\n"
        "from celofast.sdk.objects import (KnowledgeModel, Record, Attribute, KPI, Filter, Namespace)\n\n"
    )
    module = (
        header
        + "\n\n".join(declarations)
        + '\n\ndef _build_model(capture: Capture) -> CapturedKnowledgeModel:\n'
        + '    """Construct each captured object once and retain its children."""\n'
        + "\n".join(initialization)
        + f"\n    return {object_names[()]}\n"
        + (
            f'\n\n_capture = load_capture(Path(__file__).with_name("capture.json"), runtime_api={RUNTIME_API_VERSION}, digest={capture_digest(capture)!r})\n'
            f"{root_symbol}: CapturedKnowledgeModel = _build_model(_capture)\n"
            f"__all__ = [{root_symbol!r}]\n"
        )
    )
    compile(module, "<generated KM>", "exec")
    manifest = {
        "managed_by": "celofast.km",
        "runtime_api": RUNTIME_API_VERSION,
        "generator_version": GENERATOR_VERSION,
        "format_version": capture.format_version,
        "source": capture.source.model_dump(),
        "fingerprint": capture.fingerprint,
        "objects": inventory,
        "diagnostics": diagnostics,
    }
    return {
        "__init__.py": module.encode("utf-8"),
        "capture.json": capture.to_json().encode("utf-8"),
        "schema.json": (
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        ).encode("utf-8"),
        "py.typed": b"",
    }
