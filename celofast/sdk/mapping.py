"""Normalize captured records and an explicit mapping into object specifications.

Every captured record becomes an object type with a verified key or is
explicitly excluded. Every attribute of a generated type needs an expression
and a known value type, or an explicit exclusion. Relationships exist only when
declared with a target, cardinality, and field mapping. Nothing falls back to a
weaker contract: all problems are reported together as ``ObjectMappingError``.

Mapping shape (TOML, under ``[tool.celofast.knowledge-models.<name>.mapping]``
or in a separate file)::

    exclude = ["EL_CELONIS_DELIVERYLINE"]

    [objects.O_CELONIS_PLANT]
    class = "Plant"                      # optional generated class name
    key = ["ID"]                         # attribute IDs; composite keys allowed
    exclude-fields = ["LEGACY"]          # attributes not loaded
    types = { PLANTNUMBER = "str" }      # declare or override value types

    [objects.O_CELONIS_PLANT.links.materials]
    target = "O_CELONIS_MATERIALMASTERPLANT"
    cardinality = "many"                 # or "one"; "one" must target the key
    on = { ID = "PLANT_ID" }             # source attribute ID -> target attribute ID
"""

from __future__ import annotations

import keyword
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from celofast.exceptions import ObjectMappingError
from celofast.sdk.capture import Capture
from celofast.sdk.definitions import ObjectDefinition
from celofast.sdk.hydration import KEY_TYPES, ValueType
from celofast.sdk.objects import Links, Object, Relations

_COLLECTIONS = {
    "attributes": "attribute",
    "newAttributes": "new_attribute",
    "augmentedAttributes": "augmented_attribute",
}
_DECLARED_TYPES: dict[str, ValueType] = {
    "string": "str",
    "boolean": "bool",
    "integer": "int",
    "float": "float",
    "date": "date",
    "datetime": "datetime",
}
RESERVED_FIELDS = frozenset(
    {name for name in {*dir(Object), *dir(ObjectDefinition)} if not name.startswith("__")}
    | {"key", "ref", "links", "relations", "fields", "capture", "path", "object_type"}
    # Builtin annotation names used by generated fields.
    | {"str", "int", "float", "bool", "tuple"}
)
_RESERVED_CLASSES = frozenset({"ClassVar", "Path", "Any"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class LinkConfig(_Strict):
    target: str
    cardinality: Literal["one", "many"]
    on: dict[str, str] = Field(min_length=1)


class ObjectConfig(_Strict):
    class_name: str | None = Field(None, alias="class")
    key: list[str] | None = Field(None, min_length=1)
    types: dict[str, ValueType] = {}
    exclude_fields: list[str] = Field([], alias="exclude-fields")
    links: dict[str, LinkConfig] = {}


_UNMAPPED = ObjectConfig.model_validate({})


class MappingConfig(_Strict):
    exclude: list[str] = []
    objects: dict[str, ObjectConfig] = {}


@dataclass(frozen=True)
class FieldSpec:
    attribute_id: str
    path: tuple[str | int, ...]
    name: str
    value_type: ValueType
    key: bool


@dataclass(frozen=True)
class LinkSpec:
    name: str
    target: str
    cardinality: Literal["one", "many"]
    on: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ObjectSpec:
    record_id: str
    path: tuple[str | int, ...]
    class_name: str
    description: str
    fields: tuple[FieldSpec, ...]
    key: tuple[str, ...]
    links: tuple[LinkSpec, ...]


@dataclass(frozen=True)
class ModelSpec:
    objects: tuple[ObjectSpec, ...]
    excluded: tuple[str, ...]
    mapping: MappingConfig
    diagnostics: tuple[str, ...]


def python_name(value: str) -> str:
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^a-zA-Z0-9_]", "_", value).lower().strip("_") or "item"
    if value[0].isdigit():
        value = "item_" + value
    if keyword.iskeyword(value):
        value += "_"
    return value


def class_name(value: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in python_name(value).split("_") if part)


def _names(values: list[str], reserved: set[str] | frozenset[str], *, suffixes: list[str]) -> list[str]:
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
        if (
            list(candidates.values()).count(candidate) == 1
            and candidate not in reserved
            and candidate not in result
        ):
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


def _spelling(record: dict[str, Any], path: tuple[str | int, ...], attribute_id: str) -> str:
    """Prefer the data-model column name when it spells the same identifier.

    Catalog attribute IDs are often upper case (ISDISCONTINUED) while their
    column is IsDiscontinued; the column's casing yields is_discontinued.
    """
    collection, segment = path[-2], path[-1]
    items = record.get(str(collection)) or []
    attribute = (
        items[segment]
        if isinstance(segment, int)
        else next(item for item in items if isinstance(item, dict) and item.get("id") == segment)
    )
    column = attribute.get("columnName")
    if isinstance(column, str) and column.upper() == attribute_id.upper():
        return column
    return attribute_id


def parse_mapping(value: Mapping[str, Any] | MappingConfig | None) -> MappingConfig:
    if value is None:
        return MappingConfig()
    if isinstance(value, MappingConfig):
        return value
    try:
        return MappingConfig.model_validate(value)
    except ValidationError as exc:
        raise ObjectMappingError(f"Invalid KM object mapping:\n{exc}") from exc


def _segments(items: Any, expected_type: str) -> list[tuple[str | int, dict[str, Any]]]:
    """Address unique IDs by ID, and anything else by position."""
    entries = [
        (index, item)
        for index, item in enumerate(items or ())
        if isinstance(item, dict) and item.get("type") in (None, expected_type)
    ]
    ids = [item.get("id") for _, item in entries]
    return [
        (item["id"] if isinstance(item.get("id"), str) and ids.count(item["id"]) == 1 else index, item)
        for index, item in entries
    ]


def normalize(capture: Capture, mapping: Mapping[str, Any] | MappingConfig | None = None) -> ModelSpec:
    """Resolve identity, value types, and relationships, or report every gap."""
    config = parse_mapping(mapping)
    errors: list[str] = []
    diagnostics: list[str] = []
    records = {
        item["id"]: (segment, item)
        for segment, item in _segments(capture.to_dict().get("records"), "RECORD")
        if isinstance(item.get("id"), str) and item["id"]
    }
    for rid in sorted(set(config.exclude) | set(config.objects)):
        if rid not in records:
            errors.append(f"{rid}: mapped or excluded, but no such record was captured.")
    for rid in sorted(set(config.exclude) & set(config.objects)):
        errors.append(f"{rid}: both mapped and excluded; choose one.")

    drafts: list[tuple[str, tuple[str | int, ...], dict[str, Any], list[tuple[str, tuple[str | int, ...], ValueType, str]], tuple[str, ...]]] = []
    for rid, (segment, record) in sorted(records.items()):
        if rid in config.exclude:
            continue
        explicit = rid in config.objects
        settings = config.objects.get(rid, _UNMAPPED)
        problems: list[str] = []
        path: tuple[str | int, ...] = ("records", segment)
        attributes: list[tuple[str, tuple[str | int, ...], dict[str, Any], str]] = []
        for collection, suffix in _COLLECTIONS.items():
            for attribute_segment, attribute in _segments(record.get(collection), "ATTRIBUTE"):
                attribute_id = attribute.get("id")
                if not isinstance(attribute_id, str) or not attribute_id:
                    diagnostics.append(f"{rid}.{collection}[{attribute_segment}]: no ID; not generated.")
                    continue
                attributes.append((attribute_id, (*path, collection, attribute_segment), attribute, suffix))
        known = {attribute_id for attribute_id, *_ in attributes}
        for name in sorted((set(settings.exclude_fields) | set(settings.types)) - known):
            problems.append(f"mapping refers to unknown attribute {name!r}")
        included = [entry for entry in attributes if entry[0] not in settings.exclude_fields]
        ids = [attribute_id for attribute_id, *_ in included]
        for attribute_id in sorted({i for i in ids if ids.count(i) > 1}):
            problems.append(f"attribute {attribute_id!r} is defined in several collections; exclude it")
        fields: list[tuple[str, tuple[str | int, ...], ValueType, str]] = []
        for attribute_id, attribute_path, attribute, suffix in included:
            pql = attribute.get("pql")
            if not isinstance(pql, str) or not pql.strip():
                problems.append(f"attribute {attribute_id!r} has no expression; add it to exclude-fields")
                continue
            declared = attribute.get("columnType")
            value_type = settings.types.get(attribute_id) or _DECLARED_TYPES.get(
                declared.lower() if isinstance(declared, str) else ""
            )
            if value_type is None:
                problems.append(
                    f"attribute {attribute_id!r} has unknown type {declared!r}; "
                    "declare it in types or add it to exclude-fields"
                )
                continue
            fields.append((attribute_id, attribute_path, value_type, suffix))
        loaded = {attribute_id: value_type for attribute_id, _, value_type, _ in fields}
        key: tuple[str, ...] = ()
        if settings.key is not None:
            key = tuple(settings.key)
        else:
            identifier = record.get("identifier")
            expression = identifier.get("pql") if isinstance(identifier, dict) else None
            if isinstance(expression, str) and expression.strip():
                matches = [
                    attribute_id
                    for attribute_id, _, attribute, _ in included
                    if isinstance(attribute.get("pql"), str)
                    and attribute["pql"].strip() == expression.strip()
                ]
                # Celonis also projects the identifier as attributes (for
                # example ID and IDENTIFIER_AS_ATTRIBUTE). Matching expressions
                # are the same column, so the first in captured order is used.
                if matches:
                    key = (matches[0],)
                else:
                    problems.append("declared identifier matches no loaded attribute; set key")
            else:
                problems.append("no declared identifier; set key or exclude the record")
        if len(set(key)) != len(key):
            problems.append("key repeats an attribute")
        for attribute_id in key:
            if attribute_id not in loaded:
                problems.append(f"key attribute {attribute_id!r} is not a loaded field")
            elif loaded[attribute_id] not in KEY_TYPES:
                problems.append(f"key attribute {attribute_id!r} has type {loaded[attribute_id]}; keys need {', '.join(KEY_TYPES)}")
        if problems:
            hint = "" if explicit else " (map it under objects or add it to exclude)"
            errors.extend(f"{rid}{hint}: {problem}." for problem in problems)
            continue
        drafts.append((rid, path, record, fields, key))

    # Names are resolved only after every type is known, so links can use them.
    specs: dict[str, ObjectSpec] = {}
    used_classes: dict[str, str] = {}
    for rid, path, record, fields, key in drafts:
        settings = config.objects.get(rid, _UNMAPPED)
        name = settings.class_name or class_name(str(record.get("displayName") or rid))
        generated = {name, f"{name}Definition", f"{name}Links", f"{name}Relations"}
        if not name.isidentifier() or keyword.iskeyword(name) or not name[0].isupper() or name in _RESERVED_CLASSES:
            errors.append(f"{rid}: class name {name!r} must be a capitalized Python identifier; set class.")
            continue
        clashes = sorted(other for candidate in generated for other in [used_classes.get(candidate)] if other)
        if clashes:
            errors.append(f"{rid}: class name {name!r} is also used by {', '.join(clashes)}; set class.")
            continue
        used_classes.update(dict.fromkeys(generated, rid))
        names = _names(
            [_spelling(record, f[1], f[0]) for f in fields],
            RESERVED_FIELDS,
            suffixes=[f[3] for f in fields],
        )
        description = str(record.get("description") or record.get("displayName") or rid)
        specs[rid] = ObjectSpec(
            record_id=rid,
            path=path,
            class_name=name,
            description=description,
            fields=tuple(
                FieldSpec(attribute_id, attribute_path, python, value_type, attribute_id in key)
                for (attribute_id, attribute_path, value_type, _), python in zip(fields, names)
            ),
            key=tuple(names[[f[0] for f in fields].index(attribute_id)] for attribute_id in key),
            links=(),
        )

    reserved_links = {
        name for name in {*dir(Links), *dir(Relations)} if not name.startswith("__")
    }
    for rid, spec in list(specs.items()):
        links = []
        for link_name, link in sorted(config.objects.get(rid, _UNMAPPED).links.items()):
            where = f"{rid}.links.{link_name}"
            if not link_name.isidentifier() or keyword.iskeyword(link_name) or link_name.startswith("_") or link_name in reserved_links:
                errors.append(f"{where}: link name must be a public Python identifier.")
                continue
            target = specs.get(link.target)
            if target is None:
                errors.append(f"{where}: target {link.target!r} is not a generated object type.")
                continue
            source_fields = {f.attribute_id: f for f in spec.fields}
            target_fields = {f.attribute_id: f for f in target.fields}
            pairs = []
            for left, right in link.on.items():
                if left not in source_fields or right not in target_fields:
                    errors.append(f"{where}: {left!r} -> {right!r} must name loaded fields of both types.")
                elif source_fields[left].value_type != target_fields[right].value_type:
                    errors.append(f"{where}: {left!r} and {right!r} have different types.")
                else:
                    pairs.append((source_fields[left].name, target_fields[right].name))
            if len(pairs) != len(link.on):
                continue
            if link.cardinality == "one" and {right for _, right in pairs} != set(target.key):
                errors.append(f"{where}: a to-one link must map exactly the target key ({', '.join(target.key)}).")
                continue
            links.append(LinkSpec(link_name, link.target, link.cardinality, tuple(pairs)))
        specs[rid] = ObjectSpec(**{**spec.__dict__, "links": tuple(links)})

    if errors:
        raise ObjectMappingError(
            "Cannot generate identified object types. Add a mapping or an explicit "
            "exclusion for each problem:\n  - " + "\n  - ".join(errors)
        )
    return ModelSpec(
        objects=tuple(specs.values()),
        excluded=tuple(sorted(config.exclude)),
        mapping=config,
        diagnostics=tuple(diagnostics),
    )
