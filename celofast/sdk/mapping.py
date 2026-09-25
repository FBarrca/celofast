"""Derive object specifications from a KM capture and its Data Model.

A record becomes an object type when it reads a plain Data Model table with a
primary key. Its class is named after the table, its key
is the primary key, and its fields are the attributes that have an expression
and a known type: Data Model column types for plain columns, the captured result
schema (falling back to the KM's declared type) for calculated attributes. Celonis
``DATE`` values are timestamps and load as ``datetime``. Each Data Model foreign
key between two generated types gives a to-one and a to-many link. Anything that
cannot be generated is skipped and reported as a diagnostic; nothing is guessed
from names.

An event log record (``isActivityTable``) becomes an event type: the history of
the lead object the KM names for it (``eventLogsMetadata``). Celonis generates
these logs with fixed columns: ``LEAD_OBJECT_ID``, ``ID``, the activity, and
``TIMESTAMP`` become the role fields ``case``, ``event_id``, ``activity``, and
``timestamp``; the constant ``epoch`` column is not loaded. The event links to
its lead as ``case``, and the lead to its events as ``activities`` (logs named
``...Activities``) or ``events``.

An optional mapping overrides the derived model (TOML, under
``[tool.celofast.knowledge-models.<name>.mapping]`` or in a separate file)::

    exclude = ["O_CELONIS_STOCKHISTORY"]  # records not generated

    [objects.O_CELONIS_PLANT]
    class = "Site"                        # class name instead of the table's
    key = ["ID"]                          # key instead of the primary key
    exclude-fields = ["LEGACY"]           # attributes not loaded
    types = { PLANTNUMBER = "str" }       # value types instead of declared ones

    [objects.O_CELONIS_PLANT.links.materials]  # rename an automatic link,
    target = "O_CELONIS_MATERIALMASTERPLANT"   # or declare one without a
    cardinality = "many"                       # foreign key (LOOKUP joins
    on = { ID = "PLANT_ID" }                   # to-one links by value)
"""

from __future__ import annotations

import dataclasses
import keyword
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from celofast.exceptions import ObjectMappingError
from celofast.sdk.capture import Capture, record_table
from celofast.sdk.definitions import ObjectDefinition
from celofast.sdk.expressions import References, placeholders
from celofast.sdk.hydration import KEY_TYPES, ValueType
from celofast.sdk.objects import Links, Object

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
_COLUMN = re.compile(r'^\s*"([^"]+)"\."([^"]+)"\s*$')
RESERVED_FIELDS = frozenset(
    {name for name in {*dir(Object), *dir(ObjectDefinition)} if not name.startswith("__")}
    | {"key", "ref", "links", "relations", "fields", "model", "object_type", "metadata"}
    # Builtin annotation names used by generated fields.
    | {"str", "int", "float", "bool", "tuple"}
)
_RESERVED_CLASSES = frozenset({"ClassVar"})
_RESERVED_LINKS = frozenset(name for name in dir(Links) if not name.startswith("__"))


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


MappingInput = Union[Mapping[str, Any], MappingConfig, None]


@dataclass(frozen=True)
class FieldSpec:
    attribute_id: str
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
    class_name: str
    description: str
    display_name: str | None
    record_description: str | None
    fields: tuple[FieldSpec, ...]
    key: tuple[str, ...]
    links: tuple[LinkSpec, ...]
    table: str | None = None
    """The Data Model table the record reads, when its expression is a plain table."""
    lead: str | None = None
    """For an event log, the table of its lead object."""


@dataclass(frozen=True)
class ModelSpec:
    objects: tuple[ObjectSpec, ...]
    diagnostics: tuple[str, ...]


def parse_mapping(value: MappingInput) -> MappingConfig:
    if value is None:
        return MappingConfig()
    if isinstance(value, MappingConfig):
        return value
    try:
        return MappingConfig.model_validate(value)
    except ValidationError as exc:
        raise ObjectMappingError(f"Invalid KM object mapping:\n{exc}") from exc


# -- Names ------------------------------------------------------------------


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


def event_class_name(table: str) -> str:
    """``el__LineActivities`` -> ``LineActivity``; ``el_celonis_Line`` -> ``LineEvent``."""
    name = table_class_name(table)
    return name[: -len("ies")] + "y" if name.endswith("Activities") else name + "Event"


def table_class_name(table: str) -> str:
    """``o_celonis_PurchaseDocumentLine`` -> ``PurchaseDocumentLine``.

    Leading lowercase namespace segments (``o``, ``celonis``, ``r``...) are
    dropped; the rest keeps its casing.
    """
    parts = table.split("_")
    while len(parts) > 1 and parts[0].islower():
        parts.pop(0)
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


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


# -- Expressions --------------------------------------------------------------


def column(expression: str) -> tuple[str, str] | None:
    """(table, column) of a plain ``"table"."column"`` expression, else None."""
    match = _COLUMN.match(expression)
    return (match.group(1), match.group(2)) if match else None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


# -- Records ------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class _Attribute:
    """One captured attribute of a record, with what the record knows about it."""

    id: str
    collection: str
    data: dict[str, Any]
    own_column: str | None
    """The column name when the attribute is a plain column of the record's table."""

    @property
    def pql(self) -> str:
        return self.data["pql"]

    @property
    def priority(self) -> tuple[bool, bool]:
        """Prefer the attribute whose ID spells its own column (exactly, then by case)."""
        own = self.own_column
        return own == self.id, own is not None and own.casefold() == self.id.casefold()

    @property
    def spelling(self) -> str:
        """Prefer the column name when it spells the same identifier.

        Catalog attribute IDs are often upper case (ISDISCONTINUED) while their
        column is IsDiscontinued; the column's casing yields is_discontinued.
        """
        name = self.data.get("columnName")
        if not isinstance(name, str):
            found = column(self.data.get("pql", ""))
            name = found[1] if found else None
        return name if isinstance(name, str) and name.casefold() == self.id.casefold() else self.id


@dataclass(frozen=True)
class _Field:
    attribute: _Attribute
    expression: str
    """The KM expression with input-dependent references inlined; its
    placeholders are bound per read."""
    value_type: ValueType


@dataclass(frozen=True)
class _Draft:
    """A record that becomes an object type, before names are assigned."""

    record_id: str
    record: dict[str, Any]
    table: str | None
    fields: list[_Field]
    key: tuple[str, ...]
    lead: str | None = None
    """For an event log, the lead object's table."""
    roles: dict[str, str] = dataclasses.field(default_factory=dict)
    """For an event log, role field names by attribute ID."""


# Columns of Celonis-generated event logs, by role field name.
_ROLE_COLUMNS = {"case": "LEAD_OBJECT_ID", "event_id": "ID", "timestamp": "TIMESTAMP"}
_ROLE_TYPES: dict[str, tuple[ValueType, ...]] = {
    "case": KEY_TYPES, "event_id": KEY_TYPES, "activity": ("str",), "timestamp": ("datetime",),
}
_EPOCH = "epoch"


class _Normalizer:
    """Collects the errors and diagnostics of one ``normalize`` run."""

    def __init__(
        self,
        capture: Capture,
        config: MappingConfig,
        describe: Callable[[str, str, str], ValueType | None] | None,
    ) -> None:
        self.capture = capture
        self.config = config
        self.describe = describe
        self.references = References(capture)
        self.tables = {name.lower(): table for name, table in (capture.tables or {}).items()}
        metadata = capture.definition.get("eventLogsMetadata")
        logs = metadata.get("eventLogs") if isinstance(metadata, dict) else None
        self.leads: dict[str, str] = {
            log["recordId"]: log["caseTableId"] for log in logs or ()
            if isinstance(log, dict) and isinstance(log.get("recordId"), str)
            and isinstance(log.get("caseTableId"), str)
        }
        self.errors: list[str] = []
        self.diagnostics: list[str] = []

    def attributes(self, rid: str, record: dict[str, Any], table: str | None) -> list[_Attribute]:
        result = []
        for collection in _COLLECTIONS:
            for index, data in enumerate(record.get(collection) or ()):
                if not isinstance(data, dict) or data.get("type") not in (None, "ATTRIBUTE"):
                    continue
                attribute_id = data.get("id")
                if not isinstance(attribute_id, str) or not attribute_id:
                    self.diagnostics.append(f"{rid}.{collection}[{index}]: no ID; not generated.")
                    continue
                found = column(data["pql"]) if isinstance(data.get("pql"), str) else None
                own = found[1] if found and table and found[0].lower() == table.lower() else None
                result.append(_Attribute(attribute_id, collection, data, own))
        return result

    def distinct(self, rid: str, attributes: list[_Attribute], settings: ObjectConfig) -> list[_Attribute]:
        """Drop excluded, empty, and duplicate attributes.

        Only casing variants of the same attribute and expression collapse;
        distinct KM names stay distinct even when they project one column.
        """
        best: dict[tuple[str, str], _Attribute] = {}
        candidates = []
        for attribute in attributes:
            if attribute.id in settings.exclude_fields:
                continue
            pql = attribute.data.get("pql")
            if not isinstance(pql, str) or not pql.strip():
                self.diagnostics.append(f"{rid}.{attribute.id}: no expression; not generated.")
                continue
            variant = (attribute.id.casefold(), pql.strip())
            if variant not in best or attribute.priority > best[variant].priority:
                best[variant] = attribute
            candidates.append(attribute)
        # An ID must name one field; a repeat in a later collection is reported.
        first: dict[str, str] = {}
        result = []
        for attribute in candidates:
            if best[(attribute.id.casefold(), attribute.pql.strip())] is not attribute:
                continue
            if attribute.id in first:
                self.diagnostics.append(
                    f"{rid}.{attribute.collection}.{attribute.id}: ID also defined in "
                    f"{first[attribute.id]}; not generated."
                )
                continue
            first[attribute.id] = attribute.collection
            result.append(attribute)
        return result

    def field(
        self, rid: str, attribute: _Attribute, settings: ObjectConfig, dm_table: Any
    ) -> _Field | None:
        """Resolve one attribute's expression and type, or report why it is skipped."""
        where = f"{rid}.{attribute.id}"
        try:
            expression = self.references.resolve(attribute.pql)
        except ValueError as exc:
            self.diagnostics.append(f"{where}: {exc}; not generated.")
            return None
        # Input placeholders are bound at query time; each must name a KM input.
        inputs = self.capture.input_variables
        undefined = sorted(placeholders(expression) - set(inputs)) if inputs is not None else []
        if undefined:
            names = ", ".join(f"${{{name}}}" for name in undefined)
            self.diagnostics.append(f"{where}: uses {names}, which the KM does not define; not generated.")
            return None
        reason = self.capture.validation.get(rid, {}).get(attribute.id)
        if reason is not None and attribute.id not in settings.types:
            self.diagnostics.append(f"{where}: {reason}; not generated.")
            return None
        own = attribute.own_column
        declared = attribute.data.get("columnType")
        declared_type = _DECLARED_TYPES.get(declared.lower() if isinstance(declared, str) else "")
        dm_type = dm_table["columns"].get(own) if dm_table and own else None
        # Explicit overrides win, then Data Model column types, then the result
        # schema Celonis reported at pull: a calculated attribute's declared
        # type can be stale or incorrect.
        value_type = (
            settings.types.get(attribute.id)
            or (_DM_TYPES.get(dm_type.upper()) if isinstance(dm_type, str) else None)
            or self.capture.types.get(expression)
            or (declared_type if own and dm_table is None else None)
        )
        if value_type is None and self.describe is not None:
            value_type = self.describe(rid, attribute.id, expression)
        value_type = value_type or declared_type
        if value_type is None:
            self.diagnostics.append(f"{where}: unknown type {declared!r}; not generated.")
            return None
        return _Field(attribute, expression, value_type)

    def key(
        self, record: dict[str, Any], settings: ObjectConfig, dm_table: Any,
        attributes: list[_Attribute], loaded: dict[str, ValueType],
    ) -> tuple[tuple[str, ...], list[str]]:
        """The key's attribute IDs, and problems that prevent using it."""
        preferred = [a for a in sorted(attributes, key=lambda a: a.priority, reverse=True)
                     if a.id in loaded]
        problems: list[str] = []
        key: tuple[str, ...] = ()
        if settings.key is not None:
            key = tuple(settings.key)
        elif dm_table and dm_table.get("primary_key"):
            by_column: dict[str, str] = {}
            for attribute in preferred:
                if attribute.own_column is not None:
                    by_column.setdefault(attribute.own_column.lower(), attribute.id)
            missing = [c for c in dm_table["primary_key"] if c.lower() not in by_column]
            if missing:
                problems.append(f"primary key column(s) {', '.join(missing)} are not loaded attributes")
            else:
                key = tuple(by_column[c.lower()] for c in dm_table["primary_key"])
        else:
            identifier = record.get("identifier")
            expression = identifier.get("pql") if isinstance(identifier, dict) else None
            matches = [
                a.id for a in preferred
                if isinstance(expression, str) and expression.strip()
                and a.pql.strip() == expression.strip()
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
        return key, problems

    def draft(self, rid: str, record: dict[str, Any]) -> _Draft | None:
        settings = self.config.objects.get(rid, _UNMAPPED)
        table = record_table(record.get("pql"))
        dm_table = self.tables.get(table.lower()) if table else None
        attributes = self.attributes(rid, record, table)
        referenced = {*settings.exclude_fields, *settings.types}
        for name in sorted(referenced - {a.id for a in attributes}):
            self.errors.append(f"{rid}: mapping refers to unknown attribute {name!r}.")
        attributes = self.distinct(rid, attributes, settings)
        if record.get("isActivityTable"):
            return self.event_draft(rid, record, table, settings, attributes)
        fields = [f for a in attributes if (f := self.field(rid, a, settings, dm_table))]
        loaded = {f.attribute.id: f.value_type for f in fields}
        key, problems = self.key(record, settings, dm_table, attributes, loaded)
        if problems:
            if settings.key is not None:
                self.errors.extend(f"{rid}: {problem}." for problem in problems)
            else:
                self.diagnostics.extend(f"{rid}: {problem}; not an object type." for problem in problems)
            return None
        return _Draft(rid, record, table, fields, key)

    def event_draft(
        self, rid: str, record: dict[str, Any], table: str | None,
        settings: ObjectConfig, attributes: list[_Attribute],
    ) -> _Draft | None:
        """An event log: its lead, role fields, and a key of (case, event_id) by default."""
        lead = self.leads.get(rid)
        if lead is None or table is None:
            self.diagnostics.append(f"{rid}: event log without a lead object in the KM; not generated.")
            return None
        attributes = [
            a for a in attributes
            if (a.own_column or "").lower() != _EPOCH or a.id in settings.types
        ]
        fields = [f for a in attributes if (f := self.field(rid, a, settings, None))]
        by_column = {f.attribute.own_column.lower(): f for f in fields if f.attribute.own_column}
        activity_id = record.get("defaultActivityAttributeId")
        found = {role: by_column.get(column.lower()) for role, column in _ROLE_COLUMNS.items()}
        found["activity"] = next((f for f in fields if f.attribute.id == activity_id), None)
        problems = [
            f"no loaded {role} attribute" if field is None
            else f"{role} attribute {field.attribute.id!r} of type {field.value_type}"
            for role, field in found.items()
            if field is None or field.value_type not in _ROLE_TYPES[role]
        ]
        if problems:
            self.diagnostics.extend(f"{rid}: event log with {problem}; not generated." for problem in problems)
            return None
        roles = {field.attribute.id: role for role, field in found.items() if field is not None}
        default = [found[role].attribute.id for role in ("case", "event_id")]  # type: ignore[union-attr]
        loaded = {f.attribute.id: f.value_type for f in fields}
        key, problems = self.key(
            record, settings.model_copy(update={"key": settings.key or default}), None, attributes, loaded,
        )
        if problems:
            if settings.key is not None:
                self.errors.extend(f"{rid}: {problem}." for problem in problems)
            else:
                self.diagnostics.extend(f"{rid}: {problem}; not generated." for problem in problems)
            return None
        return _Draft(rid, record, table, fields, key, lead=lead, roles=roles)

    def spec(self, draft: _Draft, used_classes: dict[str, str]) -> ObjectSpec | None:
        """Name the class and its fields; ``used_classes`` tracks names taken so far."""
        rid, record = draft.record_id, draft.record
        settings = self.config.objects.get(rid, _UNMAPPED)
        naming = event_class_name if draft.lead else table_class_name
        candidates = (
            [settings.class_name] if settings.class_name
            else [c for c in (
                naming(draft.table) if draft.table else None,
                class_name(str(record.get("displayName") or rid)),
                class_name(rid),
            ) if c]
        )
        name = None
        for candidate in candidates:
            generated = {candidate, f"{candidate}Definition", f"{candidate}Links"}
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
            self.errors.append(f"{rid}: class name {settings.class_name!r} must be a capitalized Python identifier.")
            return None
        if name is None:
            message = f"{rid}: no free class name among {', '.join(candidates)}"
            (self.errors if settings.class_name else self.diagnostics).append(message + "; set class.")
            return None
        # Event role fields keep fixed names; other fields avoid them.
        others = [f for f in draft.fields if f.attribute.id not in draft.roles]
        names = _names(
            [f.attribute.spelling for f in others],
            RESERVED_FIELDS | set(draft.roles.values()),
            suffixes=[_COLLECTIONS[f.attribute.collection] for f in others],
        )
        python = {**draft.roles, **{f.attribute.id: n for f, n in zip(others, names)}}
        return ObjectSpec(
            record_id=rid,
            class_name=name,
            description=str(record.get("description") or record.get("displayName") or rid),
            display_name=_text(record.get("displayName")),
            record_description=_text(record.get("description")),
            table=draft.table,
            lead=draft.lead,
            fields=tuple(
                FieldSpec(
                    f.attribute.id,
                    python[f.attribute.id],
                    f.value_type,
                    f.attribute.id in draft.key,
                    expression=f.expression,
                    display_name=_text(f.attribute.data.get("displayName")),
                    description=_text(f.attribute.data.get("description")),
                )
                for f in draft.fields
            ),
            key=tuple(python[attribute_id] for attribute_id in draft.key),
            links=(),
        )


def normalize(
    capture: Capture, mapping: MappingInput = None,
    *, describe: Callable[[str, str, str], ValueType | None] | None = None,
) -> ModelSpec:
    """Derive object types, keys, fields, and links; apply optional overrides.

    Automatic decisions never fail: anything that cannot be generated is
    skipped and reported in ``ModelSpec.diagnostics``. Only overrides that
    refer to unknown records or attributes, or are otherwise invalid, raise
    ``ObjectMappingError``.

    ``describe(record_id, attribute_id, expression)`` is asked for the type of
    calculated attributes that no override, column, or captured type covers.
    """
    config = parse_mapping(mapping)
    run = _Normalizer(capture, config, describe)
    records = {
        record["id"]: record
        for record in capture.definition.get("records") or ()
        if isinstance(record, dict) and record.get("type") in (None, "RECORD")
        and isinstance(record.get("id"), str) and record["id"]
    }
    for rid in sorted(set(config.exclude) | set(config.objects)):
        if rid not in records:
            run.errors.append(f"{rid}: mapped or excluded, but no such record was captured.")
    for rid in sorted(set(config.exclude) & set(config.objects)):
        run.errors.append(f"{rid}: both mapped and excluded; choose one.")

    drafts = [
        draft for rid, record in sorted(records.items())
        if rid not in config.exclude and (draft := run.draft(rid, record))
    ]
    # An event log needs its lead object, identified by a single key.
    leads = {d.table.lower(): d for d in drafts if d.table and d.lead is None}
    for draft in [d for d in drafts if d.lead is not None]:
        lead = leads.get(str(draft.lead).lower())
        if lead is None or len(lead.key) != 1:
            run.diagnostics.append(
                f"{draft.record_id}: event log whose lead {draft.lead} is not a generated object "
                "type with a single key; not generated."
            )
            drafts.remove(draft)
    # Names are resolved only after every type is known, so links can use them.
    used_classes: dict[str, str] = {}
    specs = {
        spec.record_id: spec for draft in drafts if (spec := run.spec(draft, used_classes))
    }
    links = _automatic_links(capture, specs, run.diagnostics)
    _event_links(specs, links, run.diagnostics)
    _declared_links(capture, config, specs, links, run.errors, run.diagnostics)
    if run.errors:
        raise ObjectMappingError(
            "The KM object mapping has invalid overrides:\n  - " + "\n  - ".join(run.errors)
        )
    return ModelSpec(
        objects=tuple(
            dataclasses.replace(spec, links=tuple(sorted(links[rid].values(), key=lambda l: l.name)))
            for rid, spec in specs.items()
        ),
        diagnostics=tuple(run.diagnostics),
    )


# -- Links ----------------------------------------------------------------------


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

    def add(spec: ObjectSpec, link: LinkSpec, stem: str) -> None:
        _add_link(links, spec, link, stem, diagnostics)

    joins = sorted(capture.joins or (), key=lambda j: (j["one"], j["many"], j["columns"]))
    for join in joins:
        one, many = by_table.get(join["one"].lower()), by_table.get(join["many"].lower())
        if one is None or many is None:
            continue
        pairs: list[tuple[FieldSpec, FieldSpec]] = []
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
        add(many, LinkSpec(to_one, one.record_id, "one", tuple((m.name, o.name) for o, m in pairs), "fk"), stem)
        to_many = _plural(python_name(many.class_name))
        add(one, LinkSpec(to_many, many.record_id, "many", tuple((o.name, m.name) for o, m in pairs), "fk"), stem)
    return links


def _add_link(
    links: dict[str, dict[str, LinkSpec]], spec: ObjectSpec, link: LinkSpec, stem: str,
    diagnostics: list[str],
) -> None:
    """Add an automatic link; a taken name gets a ``_by_<stem>`` suffix."""
    owned = links[spec.record_id]
    name = link.name
    if name in owned or name in _RESERVED_LINKS:
        name = f"{name}_by_{stem or 'id'}"
    if name in owned:
        diagnostics.append(f"{spec.record_id}.links.{name}: name already used; not generated.")
        return
    owned[name] = dataclasses.replace(link, name=name)


def _event_links(
    specs: dict[str, ObjectSpec], links: dict[str, dict[str, LinkSpec]], diagnostics: list[str]
) -> None:
    """Link each event log and its lead object both ways.

    Celonis joins a log to its lead, so both links work in PQL as a foreign
    key would: ``BIND`` from an event, Pull-Up functions from the lead.
    """
    leads = {spec.table.lower(): spec for spec in specs.values() if spec.table and spec.lead is None}
    for spec in specs.values():
        if spec.lead is None:
            continue
        lead = leads.get(spec.lead.lower())
        types = {field.name: field.value_type for field in (lead.fields if lead else ())}
        case = next(field for field in spec.fields if field.name == "case")
        if lead is None or len(lead.key) != 1 or types[lead.key[0]] != case.value_type:
            diagnostics.append(f"{spec.record_id}: lead {spec.lead} has no matching single key; no links generated.")
            continue
        key = lead.key[0]
        _add_link(links, spec, LinkSpec("case", lead.record_id, "one", (("case", key),), "fk"), "case", diagnostics)
        name = "activities" if spec.table and spec.table.endswith("Activities") else "events"
        stem = python_name(spec.class_name)
        _add_link(links, lead, LinkSpec(name, spec.record_id, "many", ((key, "case"),), "fk"), stem, diagnostics)


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
            renamed = [owned.pop(name) for name, existing in list(owned.items())
                       if existing.target == link.target and existing.cardinality == link.cardinality
                       and set(existing.on) == set(on)]
            # A renamed automatic link keeps its join, such as an event log's lead join.
            join = next((existing.join for existing in renamed), None) or _join(
                capture.joins, spec, target, link.cardinality, pairs
            )
            if join is None:
                diagnostics.append(
                    f"{where}: no Data Model foreign key or lookup path; traversal only, "
                    "no relations predicate."
                )
            if link_name in owned:
                errors.append(f"{where}: name is already used by an automatic link.")
                continue
            owned[link_name] = LinkSpec(link_name, link.target, link.cardinality, on, join)
