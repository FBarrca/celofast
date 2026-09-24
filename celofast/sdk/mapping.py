"""Derive object specifications from a KM capture and its Data Model.

A record becomes an object type when it reads a plain Data Model table with a
primary key (event logs excepted). Its class is named after the table, its key
is the primary key, and its fields are the attributes that have an expression
and a known type: Data Model column types for plain columns, the captured result
schema (falling back to the KM's declared type) for calculated attributes. Celonis
``DATE`` values are timestamps and load as ``datetime``. Each Data Model foreign
key between two generated types gives a to-one and a to-many link. Anything that
cannot be generated is skipped and reported as a diagnostic; nothing is guessed
from names.

An optional mapping overrides the derived model (TOML, under
``[tool.celofast.knowledge-models.<name>.mapping]`` or in a separate file)::

    exclude = ["O_CELONIS_STOCKHISTORY"]  # records not generated

    [objects.O_CELONIS_PLANT]
    class = "Site"                        # class name instead of the table's
    key = ["ID"]                          # key instead of the primary key
    exclude-fields = ["LEGACY"]           # attributes not loaded
    include-fields = ["LEAD_TIME"]        # load attributes using ${...} inputs
    types = { PLANTNUMBER = "str" }       # value types instead of declared ones

    [objects.O_CELONIS_PLANT.links.materials]  # rename an automatic link,
    target = "O_CELONIS_MATERIALMASTERPLANT"   # or declare one without a
    cardinality = "many"                       # foreign key (LOOKUP joins
    on = { ID = "PLANT_ID" }                   # to-one links by value)
"""

from __future__ import annotations

import keyword
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from celofast.exceptions import ObjectMappingError
from celofast.sdk.capture import Capture
from celofast.sdk.definitions import ObjectDefinition
from celofast.sdk.expressions import Expressions
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
    # Celonis DATE values are timestamps; strict dates need a types override.
    "date": "datetime",
    "datetime": "datetime",
}
_DM_TYPES: dict[str, ValueType] = {
    "STRING": "str",
    "INTEGER": "int",
    "FLOAT": "float",
    "BOOLEAN": "bool",
    "DATE": "datetime",
}
_COMMENTS = re.compile(r"--.*?$|/\*[\s\S]*?\*/", re.MULTILINE)
_VARIABLE = re.compile(r"\$\{\w+\}")
RESERVED_FIELDS = frozenset(
    {name for name in {*dir(Object), *dir(ObjectDefinition)} if not name.startswith("__")}
    | {"key", "ref", "links", "relations", "fields", "model", "object_type", "metadata"}
    # Builtin annotation names used by generated fields.
    | {"str", "int", "float", "bool", "tuple"}
)
_RESERVED_CLASSES = frozenset({"ClassVar", "Path", "Any"})
_RESERVED_LINKS = frozenset(
    name for name in {*dir(Links), *dir(Relations)} if not name.startswith("__")
)


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
    include_fields: list[str] = Field([], alias="include-fields")
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
    expression: str
    display_name: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class LinkSpec:
    name: str
    target: str
    cardinality: Literal["one", "many"]
    on: tuple[tuple[str, str], ...]
    join: Literal["fk", "lookup"] | None = None
    """How relation predicates reach the target in PQL; None: traversal only."""


@dataclass(frozen=True)
class ObjectSpec:
    record_id: str
    path: tuple[str | int, ...]
    class_name: str
    description: str
    display_name: str | None
    record_description: str | None
    fields: tuple[FieldSpec, ...]
    key: tuple[str, ...]
    links: tuple[LinkSpec, ...]
    table: str | None = None
    """The Data Model table the record reads, when its expression is a plain table."""


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


def _attribute(record: dict[str, Any], path: tuple[str | int, ...]) -> dict[str, Any]:
    collection, segment = path[-2], path[-1]
    items = record.get(str(collection)) or []
    if isinstance(segment, int):
        return items[segment]
    return next(item for item in items if isinstance(item, dict) and item.get("id") == segment)


_TABLE = re.compile(r'^\s*"?([A-Za-z_][\w$]*)"?\s*$')
_COLUMN = re.compile(r'^\s*"([^"]+)"\."([^"]+)"\s*$')


def _table(expression: Any) -> str | None:
    match = _TABLE.match(expression) if isinstance(expression, str) else None
    return match.group(1) if match else None


def column(expression: str) -> tuple[str, str] | None:
    """(table, column) of a plain ``"table"."column"`` expression, else None."""
    match = _COLUMN.match(expression)
    return (match.group(1), match.group(2)) if match else None


def _join(
    joins: Any, source: ObjectSpec, target: ObjectSpec, cardinality: str,
    pairs: list[tuple[FieldSpec, FieldSpec]],
) -> Literal["fk", "lookup"] | None:
    """Classify how a link maps onto the Data Model.

    ``fk``: the link columns are exactly a foreign key, in the direction the
    cardinality implies (to-one: the source is the key's many side).
    ``lookup``: a to-one link on plain columns without such a key; PQL
    LOOKUP joins it by value.
    """
    if source.table is None or target.table is None:
        return None
    columns = [(column(left.expression), column(right.expression)) for left, right in pairs]
    if any(left is None or right is None for left, right in columns):
        return None
    same = lambda a, b: a.lower() == b.lower()  # noqa: E731 - PQL names ignore case
    if not all(
        same(left[0], source.table) and same(right[0], target.table)  # type: ignore[index]
        for left, right in columns
    ):
        return None
    wanted = {
        (right[1].lower(), left[1].lower()) if cardinality == "one" else (left[1].lower(), right[1].lower())  # type: ignore[index]
        for left, right in columns
    }
    one, many = (target.table, source.table) if cardinality == "one" else (source.table, target.table)
    for key in joins or ():
        if (
            same(key["one"], one)
            and same(key["many"], many)
            and {(a.lower(), b.lower()) for a, b in key["columns"]} == wanted
        ):
            return "fk"
    # LOOKUP joins by value on the single target key column.
    return "lookup" if cardinality == "one" and len(pairs) == 1 else None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _spelling(record: dict[str, Any], path: tuple[str | int, ...], attribute_id: str) -> str:
    """Prefer the data-model column name when it spells the same identifier.

    Catalog attribute IDs are often upper case (ISDISCONTINUED) while their
    column is IsDiscontinued; the column's casing yields is_discontinued.
    """
    attribute = _attribute(record, path)
    column_name = attribute.get("columnName")
    if not isinstance(column_name, str):
        found = column(attribute.get("pql", ""))
        column_name = found[1] if found else None
    if isinstance(column_name, str) and column_name.casefold() == attribute_id.casefold():
        return column_name
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


def _dm_type(value: Any) -> ValueType | None:
    """A Data Model column type; Celonis DATE columns hold timestamps."""
    return _DM_TYPES.get(value.upper()) if isinstance(value, str) else None


def _uses_variables(expression: str) -> bool:
    return _VARIABLE.search(_COMMENTS.sub("", expression)) is not None


def table_class_name(table: str) -> str:
    """``o_celonis_PurchaseDocumentLine`` -> ``PurchaseDocumentLine``.

    Leading lowercase namespace segments (``o``, ``celonis``, ``r``...) are
    dropped; the rest keeps its casing.
    """
    parts = table.split("_")
    while len(parts) > 1 and parts[0].islower():
        parts.pop(0)
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def _plural(name: str) -> str:
    if name.endswith("s"):
        return name  # Already plural, e.g. relationship_bill_of_materials.
    if name.endswith("y") and name[-2:-1] not in ("a", "e", "i", "o", "u"):
        return name[:-1] + "ies"
    if name.endswith(("x", "ch", "sh")):
        return name + "es"
    return name + "s"


def _stem(column_name: str) -> str:
    """``Header_ID`` -> ``header``; empty for a bare ``ID``."""
    stem = re.sub(r"_?id$", "", column_name, flags=re.IGNORECASE)
    return python_name(stem) if stem else ""


_Attribute = tuple[str, tuple[str | int, ...], dict[str, Any], str]
_Draft = tuple[str, tuple[str | int, ...], dict[str, Any], list[tuple[str, tuple[str | int, ...], ValueType, str]], tuple[str, ...], "str | None"]


def normalize(
    capture: Capture, mapping: Mapping[str, Any] | MappingConfig | None = None,
    *, _resolve_type: Callable[[str, str, str], ValueType | None] | None = None,
) -> ModelSpec:
    """Derive object types, keys, fields, and links; apply optional overrides.

    Automatic decisions never fail: anything that cannot be generated is
    skipped and reported in ``ModelSpec.diagnostics``. Only overrides that
    refer to unknown records or attributes, or are otherwise invalid, raise
    ``ObjectMappingError``.
    """
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
    tables = capture.tables or {}
    table_names = {name.lower(): name for name in tables}
    rejected = capture.validation
    expressions = Expressions(capture)

    drafts: list[_Draft] = []
    for rid, (segment, record) in sorted(records.items()):
        if rid in config.exclude:
            continue
        explicit = rid in config.objects
        settings = config.objects.get(rid, _UNMAPPED)
        path: tuple[str | int, ...] = ("records", segment)
        table = _table(record.get("pql"))
        dm_table = tables.get(table_names.get(table.lower(), "")) if table else None
        if record.get("isActivityTable") and not explicit:
            diagnostics.append(f"{rid}: event log; not an object type.")
            continue

        attributes: list[_Attribute] = []
        for collection, suffix in _COLLECTIONS.items():
            for attribute_segment, attribute in _segments(record.get(collection), "ATTRIBUTE"):
                attribute_id = attribute.get("id")
                if not isinstance(attribute_id, str) or not attribute_id:
                    diagnostics.append(f"{rid}.{collection}[{attribute_segment}]: no ID; not generated.")
                    continue
                attributes.append((attribute_id, (*path, collection, attribute_segment), attribute, suffix))
        known = {attribute_id for attribute_id, *_ in attributes}
        referenced = set(settings.exclude_fields) | set(settings.types) | set(settings.include_fields)
        for name in sorted(referenced - known):
            errors.append(f"{rid}: mapping refers to unknown attribute {name!r}.")

        def column_of(attribute: dict[str, Any]) -> str | None:
            """The column name when the attribute is a plain column of this record's table."""
            expression = attribute.get("pql")
            found = column(expression) if isinstance(expression, str) else None
            if found is None or table is None or found[0].lower() != table.lower():
                return None
            return found[1]

        # Collapse only casing variants of the same attribute and expression.
        # Distinct KM names remain distinct even when they project one column.
        def priority(entry: _Attribute) -> tuple[bool, bool]:
            own_column = column_of(entry[2])
            return (
                own_column == entry[0],
                own_column is not None and own_column.casefold() == entry[0].casefold(),
            )

        chosen: dict[tuple[str, str], _Attribute] = {}
        attribute_candidates: list[_Attribute] = []
        for entry in attributes:
            attribute_id, _, attribute, _ = entry
            if attribute_id in settings.exclude_fields:
                continue
            expression = attribute.get("pql")
            if not isinstance(expression, str) or not expression.strip():
                diagnostics.append(f"{rid}.{attribute_id}: no expression; not generated.")
                continue
            normalized = (attribute_id.casefold(), expression.strip())
            current = chosen.get(normalized)
            if current is None or priority(entry) > priority(current):
                chosen[normalized] = entry
            attribute_candidates.append(entry)
        included = []
        # An ID must name one field; a repeat in a later collection is reported.
        first_collection: dict[str, str | int] = {}
        for entry in attribute_candidates:
            if entry != chosen[(entry[0].casefold(), entry[2]["pql"].strip())]:
                continue
            collection = entry[1][-2]
            if entry[0] in first_collection:
                diagnostics.append(
                    f"{rid}.{collection}.{entry[0]}: ID also defined in "
                    f"{first_collection[entry[0]]}; not generated."
                )
                continue
            first_collection[entry[0]] = collection
            included.append(entry)

        fields: list[tuple[str, tuple[str | int, ...], ValueType, str]] = []
        for attribute_id, attribute_path, attribute, suffix in included:
            expression = attribute["pql"]
            if _uses_variables(expression) and attribute_id not in settings.include_fields:
                diagnostics.append(
                    f"{rid}.{attribute_id}: uses KM input variables; add it to include-fields "
                    "to load it."
                )
                continue
            try:
                expression = expressions.resolve(
                    expression, bind_defaults=attribute_id not in settings.include_fields,
                )
            except ValueError as exc:
                diagnostics.append(f"{rid}.{attribute_id}: {exc}; not generated.")
                continue
            if _uses_variables(expression) and attribute_id not in settings.include_fields:
                diagnostics.append(
                    f"{rid}.{attribute_id}: calculated dependency needs KM input values; "
                    "set input defaults or add it to include-fields."
                )
                continue
            reason = rejected.get(rid, {}).get(attribute_id)
            if reason is not None and attribute_id not in settings.types:
                diagnostics.append(f"{rid}.{attribute_id}: {reason}; not generated.")
                continue
            own_column = column_of(attribute)
            declared = attribute.get("columnType")
            declared_type = _DECLARED_TYPES.get(declared.lower() if isinstance(declared, str) else "")
            value_type = (
                settings.types.get(attribute_id)
                or (_dm_type(dm_table["columns"].get(own_column)) if dm_table and own_column else None)
                or capture.types.get(expression)
                or (declared_type if own_column and dm_table is None else None)
            )
            # A calculated attribute's declared type can be stale or incorrect.
            # Prefer the actual result schema; explicit overrides and catalog
            # column types already took precedence above.
            if value_type is None and _resolve_type is not None and not _uses_variables(expression):
                value_type = _resolve_type(rid, attribute_id, expression)
            value_type = value_type or declared_type
            if value_type is None:
                diagnostics.append(f"{rid}.{attribute_id}: unknown type {declared!r}; not generated.")
                continue
            attribute["pql"] = expression  # Detached copy; the capture and live KM are unchanged.
            fields.append((attribute_id, attribute_path, value_type, suffix))
        loaded = {attribute_id: value_type for attribute_id, _, value_type, _ in fields}
        by_column: dict[str, str] = {}
        for attribute_id, _, attribute, _ in sorted(included, key=priority, reverse=True):
            own = column_of(attribute)
            if own is not None and attribute_id in loaded:
                by_column.setdefault(own.lower(), attribute_id)

        problems: list[str] = []
        key: tuple[str, ...] = ()
        if settings.key is not None:
            key = tuple(settings.key)
        elif dm_table and dm_table.get("primary_key"):
            missing = [c for c in dm_table["primary_key"] if c.lower() not in by_column]
            if missing:
                problems.append(f"primary key column(s) {', '.join(missing)} are not loaded attributes")
            else:
                key = tuple(by_column[c.lower()] for c in dm_table["primary_key"])
        else:
            identifier = record.get("identifier")
            expression = identifier.get("pql") if isinstance(identifier, dict) else None
            matches = [
                attribute_id
                for attribute_id, _, attribute, _ in sorted(included, key=priority, reverse=True)
                if isinstance(expression, str) and expression.strip()
                and attribute_id in loaded
                and attribute["pql"].strip() == expression.strip()
            ]
            if matches:
                key = (matches[0],)
            else:
                problems.append("no primary key or declared identifier")
        if len(set(key)) != len(key):
            problems.append("key repeats an attribute")
        for attribute_id in key:
            if attribute_id not in loaded:
                problems.append(f"key attribute {attribute_id!r} is not a loaded field")
            elif loaded[attribute_id] not in KEY_TYPES:
                problems.append(f"key attribute {attribute_id!r} has type {loaded[attribute_id]}")
        if problems:
            if settings.key is not None:
                errors.extend(f"{rid}: {problem}." for problem in problems)
            else:
                diagnostics.extend(f"{rid}: {problem}; not an object type." for problem in problems)
            continue
        drafts.append((rid, path, record, fields, key, table))

    # Names are resolved only after every type is known, so links can use them.
    specs: dict[str, ObjectSpec] = {}
    used_classes: dict[str, str] = {}
    for rid, path, record, fields, key, table in drafts:
        settings = config.objects.get(rid, _UNMAPPED)
        candidates = (
            [settings.class_name] if settings.class_name
            else [c for c in (
                table_class_name(table) if table else None,
                class_name(str(record.get("displayName") or rid)),
                class_name(rid),
            ) if c]
        )
        name = None
        for candidate in candidates:
            generated = {candidate, f"{candidate}Definition", f"{candidate}Links", f"{candidate}Relations"}
            valid = (
                candidate.isidentifier() and not keyword.iskeyword(candidate)
                and candidate[0].isupper() and candidate not in _RESERVED_CLASSES
            )
            if valid and not any(other in used_classes for other in generated):
                name = candidate
                used_classes.update(dict.fromkeys(generated, rid))
                break
        if name is None and settings.class_name and not (
            settings.class_name.isidentifier() and settings.class_name[0].isupper()
        ):
            errors.append(f"{rid}: class name {settings.class_name!r} must be a capitalized Python identifier.")
            continue
        if name is None:
            message = f"{rid}: no free class name among {', '.join(candidates)}"
            (errors if settings.class_name else diagnostics).append(message + "; set class.")
            continue
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
            display_name=_text(record.get("displayName")),
            record_description=_text(record.get("description")),
            table=table,
            fields=tuple(
                FieldSpec(
                    attribute_id,
                    attribute_path,
                    python,
                    value_type,
                    attribute_id in key,
                    expression=_attribute(record, attribute_path)["pql"],
                    display_name=_text(_attribute(record, attribute_path).get("displayName")),
                    description=_text(_attribute(record, attribute_path).get("description")),
                )
                for (attribute_id, attribute_path, value_type, _), python in zip(fields, names)
            ),
            key=tuple(names[[f[0] for f in fields].index(attribute_id)] for attribute_id in key),
            links=(),
        )

    links = _automatic_links(capture, specs, diagnostics)
    _declared_links(capture, config, specs, links, errors, diagnostics)
    for rid, spec in list(specs.items()):
        specs[rid] = ObjectSpec(**{**spec.__dict__, "links": tuple(sorted(links[rid].values(), key=lambda link: link.name))})

    if errors:
        raise ObjectMappingError(
            "The KM object mapping has invalid overrides:\n  - " + "\n  - ".join(errors)
        )
    return ModelSpec(
        objects=tuple(specs.values()),
        excluded=tuple(sorted(config.exclude)),
        mapping=config,
        diagnostics=tuple(diagnostics),
    )


def _field_for_column(spec: ObjectSpec, name: str) -> FieldSpec | None:
    matches = []
    for field in spec.fields:
        found = column(field.expression)
        if found and spec.table and found[0].lower() == spec.table.lower() and found[1].lower() == name.lower():
            matches.append(field)
    return max(matches, key=lambda field: (
        field.key, field.attribute_id == name, field.attribute_id.casefold() == name.casefold(),
    ), default=None)


def _automatic_links(
    capture: Capture, specs: dict[str, ObjectSpec], diagnostics: list[str]
) -> dict[str, dict[str, LinkSpec]]:
    """A to-one and a to-many link for every foreign key between generated types."""
    by_table = {spec.table.lower(): spec for spec in specs.values() if spec.table}
    links: dict[str, dict[str, LinkSpec]] = {rid: {} for rid in specs}

    def add(spec: ObjectSpec, name: str, link: LinkSpec, stem: str) -> None:
        owned = links[spec.record_id]
        if name in owned or name in _RESERVED_LINKS:
            name = f"{name}_by_{stem or 'id'}"
        if name in owned:
            diagnostics.append(f"{spec.record_id}.links.{name}: name already used; not generated.")
            return
        owned[name] = LinkSpec(name, link.target, link.cardinality, link.on, link.join)

    for join in capture.joins or ():
        one, many = by_table.get(join["one"].lower()), by_table.get(join["many"].lower())
        if one is None or many is None:
            continue
        pairs = []
        for one_column, many_column in join["columns"]:
            one_field, many_field = _field_for_column(one, one_column), _field_for_column(many, many_column)
            if one_field is None or many_field is None or one_field.value_type != many_field.value_type:
                pairs = []
                break
            pairs.append((one_field, many_field))
        if not pairs or {one_field.name for one_field, _ in pairs} != set(one.key):
            diagnostics.append(
                f"{many.record_id} -> {one.record_id}: foreign key does not match loaded key fields; "
                "no link generated."
            )
            continue
        stem = _stem(join["columns"][0][1]) if len(pairs) == 1 else ""
        to_one = stem or python_name(one.class_name)
        add(many, to_one, LinkSpec(to_one, one.record_id, "one",
                                   tuple((m.name, o.name) for o, m in pairs), "fk"), stem)
        to_many = _plural(python_name(many.class_name))
        add(one, to_many, LinkSpec(to_many, many.record_id, "many",
                                   tuple((o.name, m.name) for o, m in pairs), "fk"), stem)
    return links


def _declared_links(
    capture: Capture,
    config: MappingConfig,
    specs: dict[str, ObjectSpec],
    links: dict[str, dict[str, LinkSpec]],
    errors: list[str],
    diagnostics: list[str],
) -> None:
    """Declared links rename a matching automatic link, or add a new one."""
    for rid, spec in specs.items():
        for link_name, link in sorted(config.objects.get(rid, _UNMAPPED).links.items()):
            where = f"{rid}.links.{link_name}"
            if (
                not link_name.isidentifier() or keyword.iskeyword(link_name)
                or link_name.startswith("_") or link_name in _RESERVED_LINKS
            ):
                errors.append(f"{where}: link name must be a public Python identifier.")
                continue
            target = specs.get(link.target)
            if target is None:
                errors.append(f"{where}: target {link.target!r} is not a generated object type.")
                continue
            source_fields = {f.attribute_id: f for f in spec.fields}
            target_fields = {f.attribute_id: f for f in target.fields}
            pairs: list[tuple[FieldSpec, FieldSpec]] = []
            for left, right in link.on.items():
                if left not in source_fields or right not in target_fields:
                    errors.append(f"{where}: {left!r} -> {right!r} must name loaded fields of both types.")
                elif source_fields[left].value_type != target_fields[right].value_type:
                    errors.append(f"{where}: {left!r} and {right!r} have different types.")
                else:
                    pairs.append((source_fields[left], target_fields[right]))
            if len(pairs) != len(link.on):
                continue
            if link.cardinality == "one" and {right.name for _, right in pairs} != set(target.key):
                errors.append(f"{where}: a to-one link must map exactly the target key ({', '.join(target.key)}).")
                continue
            on = tuple((left.name, right.name) for left, right in pairs)
            owned = links[rid]
            for automatic in [name for name, existing in owned.items()
                              if existing.target == link.target and existing.cardinality == link.cardinality
                              and set(existing.on) == set(on)]:
                del owned[automatic]  # Renamed by the declaration.
            join = _join(capture.joins, spec, target, link.cardinality, pairs)
            if join is None:
                diagnostics.append(
                    f"{where}: no Data Model foreign key or lookup path; traversal only, "
                    "no relations predicate."
                )
            if link_name in owned:
                errors.append(f"{where}: name is already used by an automatic link.")
                continue
            owned[link_name] = LinkSpec(link_name, link.target, link.cardinality, on, join)
