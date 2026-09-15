"""Deterministic explicit Python declarations from a complete KM capture."""

from __future__ import annotations

import hashlib
import json
import keyword
import re
from typing import Any

from celofast.sdk.capture import Capture
from celofast.sdk.loading import RUNTIME_API_VERSION, capture_digest
from celofast.sdk.objects import Attribute, KnowledgeModel, KnowledgeObject, Namespace

GENERATOR_VERSION = 2


def _has_objects(value: Any) -> bool:
    """Plain metadata stays in metadata; only definition objects need symbols."""
    if isinstance(value, dict):
        return any(key in value for key in ("id", "type", "pql")) or any(
            _has_objects(item) for item in value.values()
        )
    return isinstance(value, list) and any(
        isinstance(item, dict) or _has_objects(item) for item in value
    )


def python_name(value: str) -> str:
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^a-zA-Z0-9_]", "_", value).lower().strip("_") or "item"
    if value[0].isdigit():
        value = "item_" + value
    if keyword.iskeyword(value):
        value += "_"
    return value


def _names(values: list[str], reserved: set[str]) -> list[str]:
    names = [python_name(value) for value in values]
    result = []
    for index, (value, name) in enumerate(zip(values, names)):
        if names.count(name) > 1 or name in reserved:
            identity = f"{index}:{value}" if values.count(value) > 1 else value
            digest = hashlib.sha256(identity.encode()).hexdigest()[:12]
            name += "_" + digest
        while name in result or name in reserved:
            name += "_"
        result.append(name)
    return result


def generate(capture: Capture) -> dict[str, bytes]:
    """Render a self-contained typed package without touching the filesystem."""
    declarations: list[str] = []
    inventory: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    object_classes: dict[tuple[str | int, ...], str] = {}
    class_names: dict[str, tuple[str | int, ...] | None] = dict.fromkeys(
        {
            "KnowledgeModel",
            "Record",
            "Attribute",
            "KPI",
            "Filter",
            "Variable",
            "GenericKnowledgeObject",
            "Namespace",
            "Path",
            "Any",
            "CapturedKnowledgeModel",
        }
    )
    reserved = (
        set(dir(KnowledgeObject))
        | set(dir(KnowledgeModel))
        | set(dir(Attribute))
        | set(dir(Namespace))
        | {"capture", "path", "_handle"}
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
        if name in class_names and class_names[name] != path:
            name += hashlib.sha256(json.dumps(path).encode()).hexdigest()[:12]
        class_names[name] = path
        return name

    def base_for(value: dict[str, Any], path: tuple[str | int, ...]) -> str:
        if not path:
            return "KnowledgeModel"
        category = value.get("type")
        collection = path[-2] if len(path) >= 2 else None
        base = {
            "RECORD": "Record",
            "ATTRIBUTE": "Attribute",
            "KPI": "KPI",
            "FILTER": "Filter",
            "VARIABLE": "Variable",
        }.get(category if isinstance(category, str) else "")
        if base is None:
            base = {
                "records": "Record",
                "attributes": "Attribute",
                "newAttributes": "Attribute",
                "augmentedAttributes": "Attribute",
                "kpis": "KPI",
                "filters": "Filter",
                "variables": "Variable",
            }.get(
                collection if isinstance(collection, str) else "",
                "GenericKnowledgeObject",
            )
        if base in {"Attribute", "KPI", "Variable"}:
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

    def emit(value: Any, path: tuple[str | int, ...], access: str) -> str:
        name = class_name(path)
        properties = []
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
            if base == "GenericKnowledgeObject":
                diagnostics.append(f"{path!r}: represented as GenericKnowledgeObject")
            children = [
                (key, item)
                for key, item in value.items()
                if _has_objects(item)
                or isinstance(item, list)
                and not item
                and (not path or base == "Record")
            ]
            if not children and path:
                object_classes[path] = base
                return base
            symbols = _names([key for key, _ in children], reserved)
            for (key, child), symbol in zip(children, symbols):
                child_path = (*path, key)
                child_class = emit(child, child_path, f"{access}.{symbol}")
                # Bind the constructor now: importlib.reload replaces module
                # globals, but existing objects must retain their old hierarchy.
                properties.extend(
                    [
                        "    @property",
                        f"    def {symbol}(self, _type: type[{child_class}] = {child_class}) -> {child_class}:",
                        f"        return _type(self.capture, {child_path!r})",
                        "",
                    ]
                )
            if base == "Record":
                # Shortcuts never replace metadata, children, or an ambiguous
                # attribute name. The original collections remain canonical.
                attributes = [
                    entry
                    for entry in inventory
                    if len(entry["path"]) == len(path) + 2
                    and tuple(entry["path"][: len(path)]) == path
                    and entry["path"][-2]
                    in {
                        "attributes",
                        "newAttributes",
                        "augmentedAttributes",
                    }
                    and isinstance(entry["id"], str)
                    and entry["class"].startswith("Attribute[")
                ]
                aliases = [python_name(entry["id"]) for entry in attributes]
                for entry, alias in zip(attributes, aliases):
                    if alias in reserved or alias in symbols or aliases.count(alias) > 1:
                        continue
                    child_class = object_classes[tuple(entry["path"])]
                    relative = entry["python"][len(access) + 1 :]
                    properties.extend(
                        [
                            "    @property",
                            f"    def {alias}(self) -> {child_class}:",
                            f"        return self.{relative}",
                            "",
                        ]
                    )
        else:
            base = "Namespace"
            entries = [
                (index, item)
                for index, item in enumerate(value)
                if isinstance(item, dict)
                or isinstance(item, list)
                and _has_objects(item)
            ]
            if not entries:
                return "Namespace"
            symbols = _names(
                [
                    str(item.get("id") or f"item_{index}")
                    if isinstance(item, dict)
                    else f"item_{index}"
                    for index, item in entries
                ],
                reserved,
            )
            members = []
            for (index, child), symbol in zip(entries, symbols):
                child_id = child.get("id") if isinstance(child, dict) else None
                child_path = (
                    *path,
                    child_id
                    if isinstance(child_id, str)
                    and sum(
                        isinstance(item, dict) and item.get("id") == child_id
                        for _, item in entries
                    )
                    == 1
                    else index,
                )
                child_class = emit(child, child_path, f"{access}.{symbol}")
                if isinstance(child, dict):
                    members.append((child_id, symbol))
                description = (
                    (
                        child.get("description")
                        or child.get("displayName")
                        or child_id
                        or symbol
                    )
                    if isinstance(child, dict)
                    else symbol
                )
                properties.extend(
                    [
                        "    @property",
                        f"    def {symbol}(self, _type: type[{child_class}] = {child_class}) -> {child_class}:",
                        f"        {str(description)!r}",
                        f"        return _type(self.capture, {child_path!r})",
                        "",
                    ]
                )
            properties.insert(0, f"    _members = {tuple(members)!r}\n")
        declarations.append(
            f"@dataclass(frozen=True)\nclass {name}({base}):\n"
            + ("\n".join(properties) or "    pass\n")
        )
        object_classes[path] = name
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
        "from celofast.sdk.loading import load_capture\n"
        "from celofast.sdk.objects import (KnowledgeModel, Record, Attribute, KPI, Filter, Variable, GenericKnowledgeObject, Namespace)\n\n"
    )
    module = (
        header
        + "\n\n".join(declarations)
        + (
            f'\n\n_capture = load_capture(Path(__file__).with_name("capture.json"), runtime_api={RUNTIME_API_VERSION}, digest={capture_digest(capture)!r})\n'
            f"{root_symbol} = CapturedKnowledgeModel(_capture)\n"
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
