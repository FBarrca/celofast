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
"""

from __future__ import annotations

import dataclasses
import keyword
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

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
    # Celonis DATE values are timestamps.
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
_RESERVED_LINKS = frozenset(name for name in dir(Links) if not name.startswith("__"))


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


# Columns of Celonis-generated event logs, by role field name.
_ROLE_COLUMNS = {"case": "LEAD_OBJECT_ID", "event_id": "ID", "timestamp": "TIMESTAMP"}
_ROLE_TYPES: dict[str, tuple[ValueType, ...]] = {
    "case": KEY_TYPES, "event_id": KEY_TYPES, "activity": ("str",), "timestamp": ("datetime",),
}
_EPOCH = "epoch"


class _Normalizer:
    """Builds the object specs of one ``normalize`` run and collects its diagnostics."""

    def __init__(
        self,
        capture: Capture,
        describe: Callable[[str, str, str], ValueType | None] | None,
    ) -> None:
        self.capture = capture
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
        self.classes: set[str] = set()
        self.diagnostics: list[str] = []

    def attributes(self, rid: str, record: dict[str, Any], table: str | None) -> list[_Attribute]:
        """The record's attributes, without empty and duplicate ones.

        Only casing variants of the same attribute and expression collapse;
        distinct KM names stay distinct even when they project one column.
        """
        found: list[_Attribute] = []
        for collection in _COLLECTIONS:
            for index, data in enumerate(record.get(collection) or ()):
                if not isinstance(data, dict) or data.get("type") not in (None, "ATTRIBUTE"):
                    continue
                attribute_id, pql = data.get("id"), data.get("pql")
                if not isinstance(attribute_id, str) or not attribute_id:
                    self.diagnostics.append(f"{rid}.{collection}[{index}]: no ID; not generated.")
                elif not isinstance(pql, str) or not pql.strip():
                    self.diagnostics.append(f"{rid}.{attribute_id}: no expression; not generated.")
                else:
                    plain = column(pql)
                    own = plain[1] if plain and table and plain[0].lower() == table.lower() else None
                    found.append(_Attribute(attribute_id, collection, data, own))
        best: dict[tuple[str, str], _Attribute] = {}
        for attribute in found:
            variant = (attribute.id.casefold(), attribute.pql.strip())
            if variant not in best or attribute.priority > best[variant].priority:
                best[variant] = attribute
        # An ID must name one field; a repeat in a later collection is reported.
        first: dict[str, str] = {}
        result = []
        for attribute in found:
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

    def field(self, rid: str, attribute: _Attribute, dm_table: Any) -> _Field | None:
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
        if reason is not None:
            self.diagnostics.append(f"{where}: {reason}; not generated.")
            return None
        own = attribute.own_column
        declared = attribute.data.get("columnType")
        declared_type = _DECLARED_TYPES.get(declared.lower() if isinstance(declared, str) else "")
        dm_type = dm_table["columns"].get(own) if dm_table and own else None
        # Data Model column types win, then the result schema Celonis reported
        # at pull: a calculated attribute's declared type can be stale or incorrect.
        value_type = (
            (_DM_TYPES.get(dm_type.upper()) if isinstance(dm_type, str) else None)
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

    def key(self, record: dict[str, Any], dm_table: Any, fields: list[_Field]) -> tuple[str, ...] | str:
        """The key's attribute IDs: the primary key, else the declared identifier.

        Returns the reason when there is no usable key.
        """
        preferred = sorted((f.attribute for f in fields), key=lambda a: a.priority, reverse=True)
        if dm_table and dm_table.get("primary_key"):
            by_column: dict[str, str] = {}
            for attribute in preferred:
                if attribute.own_column is not None:
                    by_column.setdefault(attribute.own_column.lower(), attribute.id)
            missing = [c for c in dm_table["primary_key"] if c.lower() not in by_column]
            if missing:
                return f"primary key column(s) {', '.join(missing)} are not loaded attributes"
            key = tuple(by_column[c.lower()] for c in dm_table["primary_key"])
        else:
            identifier = record.get("identifier")
            expression = identifier.get("pql") if isinstance(identifier, dict) else None
            matches = [
                a.id for a in preferred
                if isinstance(expression, str) and expression.strip() and a.pql.strip() == expression.strip()
            ]
            if not matches:
                return "no primary key or declared identifier"
            key = (matches[0],)
        types = {f.attribute.id: f.value_type for f in fields}
        wrong = [f"key attribute {a!r} has type {types[a]}" for a in key if types[a] not in KEY_TYPES]
        return wrong[0] if wrong else key

    def roles(self, record: dict[str, Any], fields: list[_Field]) -> dict[str, str] | str:
        """An event log's role field names by attribute ID, or why it has none."""
        by_column = {f.attribute.own_column.lower(): f for f in fields if f.attribute.own_column}
        found = {role: by_column.get(column.lower()) for role, column in _ROLE_COLUMNS.items()}
        found["activity"] = next(
            (f for f in fields if f.attribute.id == record.get("defaultActivityAttributeId")), None
        )
        for role, field in found.items():
            if field is None:
                return f"no loaded {role} attribute"
            if field.value_type not in _ROLE_TYPES[role]:
                return f"{role} attribute {field.attribute.id!r} of type {field.value_type}"
        return {field.attribute.id: role for role, field in found.items() if field is not None}

    def spec(self, rid: str, record: dict[str, Any]) -> ObjectSpec | None:
        table = record_table(record.get("pql"))
        lead = self.leads.get(rid) if record.get("isActivityTable") else None
        if record.get("isActivityTable") and (lead is None or table is None):
            self.diagnostics.append(f"{rid}: event log without a lead object in the KM; not generated.")
            return None
        # Event logs are not Data Model tables; their constant epoch column is not loaded.
        dm_table = None if lead else self.tables.get(table.lower()) if table else None
        attributes = [
            a for a in self.attributes(rid, record, table)
            if not lead or (a.own_column or "").lower() != _EPOCH
        ]
        fields = [f for a in attributes if (f := self.field(rid, a, dm_table))]
        roles: dict[str, str] = {}
        if lead:
            found = self.roles(record, fields)
            if isinstance(found, str):
                self.diagnostics.append(f"{rid}: event log with {found}; not generated.")
                return None
            roles = found
            by_role = {role: attribute_id for attribute_id, role in roles.items()}
            key: tuple[str, ...] | str = (by_role["case"], by_role["event_id"])
        else:
            key = self.key(record, dm_table, fields)
        if isinstance(key, str):
            self.diagnostics.append(f"{rid}: {key}; not an object type.")
            return None
        naming = event_class_name if lead else table_class_name
        candidates = [c for c in (naming(table) if table else None, class_name(str(record.get("displayName") or rid)))
                      if c and c.isidentifier() and c[0].isupper() and not keyword.iskeyword(c)]
        free = [c for c in candidates if not {c, f"{c}Definition", f"{c}Links"} & self.classes]
        if not free:
            self.diagnostics.append(f"{rid}: no free class name among {', '.join(candidates)}; not generated.")
            return None
        name = free[0]
        self.classes |= {name, f"{name}Definition", f"{name}Links"}
        # Event role fields keep fixed names; other fields avoid them.
        others = [f for f in fields if f.attribute.id not in roles]
        names = _names(
            [f.attribute.spelling for f in others],
            RESERVED_FIELDS | set(roles.values()),
            suffixes=[_COLLECTIONS[f.attribute.collection] for f in others],
        )
        python = {**roles, **{f.attribute.id: n for f, n in zip(others, names)}}
        return ObjectSpec(
            record_id=rid,
            class_name=name,
            description=str(record.get("description") or record.get("displayName") or rid),
            display_name=_text(record.get("displayName")),
            record_description=_text(record.get("description")),
            table=table,
            lead=lead,
            fields=tuple(
                FieldSpec(
                    f.attribute.id,
                    python[f.attribute.id],
                    f.value_type,
                    f.attribute.id in key,
                    expression=f.expression,
                    display_name=_text(f.attribute.data.get("displayName")),
                    description=_text(f.attribute.data.get("description")),
                )
                for f in fields
            ),
            key=tuple(python[attribute_id] for attribute_id in key),
            links=(),
        )


def normalize(
    capture: Capture, *, describe: Callable[[str, str, str], ValueType | None] | None = None,
) -> ModelSpec:
    """Derive object types, keys, fields, and links.

    Never fails: anything that cannot be generated is skipped and reported in
    ``ModelSpec.diagnostics``.

    ``describe(record_id, attribute_id, expression)`` is asked for the type of
    calculated attributes that no column or captured type covers.
    """
    run = _Normalizer(capture, describe)
    records = {
        record["id"]: record
        for record in capture.definition.get("records") or ()
        if isinstance(record, dict) and record.get("type") in (None, "RECORD")
        and isinstance(record.get("id"), str) and record["id"]
    }
    specs = {rid: spec for rid, record in sorted(records.items()) if (spec := run.spec(rid, record))}
    links = _links(capture, specs, run.diagnostics)
    return ModelSpec(
        objects=tuple(
            dataclasses.replace(spec, links=tuple(sorted(links[rid].values(), key=lambda l: l.name)))
            for rid, spec in specs.items()
        ),
        diagnostics=tuple(run.diagnostics),
    )


# -- Links ----------------------------------------------------------------------


def _field_for_column(spec: ObjectSpec, name: str) -> FieldSpec | None:
    matches = []
    for field in spec.fields:
        found = column(field.expression)
        if found and spec.table and found[0].lower() == spec.table.lower() and found[1].lower() == name.lower():
            matches.append(field)
    return max(matches, key=lambda field: (
        field.key, field.attribute_id == name, field.attribute_id.casefold() == name.casefold(),
    ), default=None)


def _links(
    capture: Capture, specs: dict[str, ObjectSpec], diagnostics: list[str]
) -> dict[str, dict[str, LinkSpec]]:
    """A to-one and a to-many link for every foreign key between generated
    types, and between each event log and its lead object.

    Celonis joins a log to its lead, so those links work in PQL like foreign
    key links: ``BIND`` from an event, Pull-Up functions from the lead. An
    event log whose lead is not a generated type with a matching single key
    is dropped.
    """
    objects = {spec.table.lower(): spec for spec in specs.values() if spec.table and not spec.lead}
    links: dict[str, dict[str, LinkSpec]] = {rid: {} for rid in specs}

    def add(spec: ObjectSpec, link: LinkSpec, stem: str) -> None:
        owned = links[spec.record_id]
        name = link.name
        if name in owned or name in _RESERVED_LINKS:
            name = f"{name}_by_{stem or 'id'}"
        if name in owned:
            diagnostics.append(f"{spec.record_id}.links.{name}: name already used; not generated.")
            return
        owned[name] = dataclasses.replace(link, name=name)

    for join in sorted(capture.joins or (), key=lambda j: (j["one"], j["many"], j["columns"])):
        one, many = objects.get(join["one"].lower()), objects.get(join["many"].lower())
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
        add(many, LinkSpec(stem or python_name(one.class_name), one.record_id, "one",
                           tuple((m.name, o.name) for o, m in pairs)), stem)
        add(one, LinkSpec(_plural(python_name(many.class_name)), many.record_id, "many",
                          tuple((o.name, m.name) for o, m in pairs)), stem)

    for log in [spec for spec in specs.values() if spec.lead]:
        lead = objects.get(str(log.lead).lower())
        case = next(field for field in log.fields if field.name == "case")
        types = {field.name: field.value_type for field in lead.fields} if lead else {}
        if lead is None or len(lead.key) != 1 or types[lead.key[0]] != case.value_type:
            diagnostics.append(
                f"{log.record_id}: event log whose lead {log.lead} is not a generated object "
                "type with a single matching key; not generated."
            )
            del specs[log.record_id], links[log.record_id]
            continue
        key = lead.key[0]
        add(log, LinkSpec("case", lead.record_id, "one", (("case", key),)), "case")
        name = "activities" if str(log.table).endswith("Activities") else "events"
        add(lead, LinkSpec(name, log.record_id, "many", ((key, "case"),)), python_name(log.class_name))
    return links
