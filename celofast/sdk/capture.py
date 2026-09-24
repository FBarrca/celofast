"""Lossless, offline captures of effective Knowledge Model definitions."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from functools import cached_property
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

if TYPE_CHECKING:
    from celofast.sdk.hydration import ValueType

FORMAT_VERSION: Literal[1] = 1

# Only collections whose KM semantics are keyed by ID are reordered. Arbitrary
# metadata arrays, parameters, priorities, and unknown collections retain order.
_ROOT_COLLECTIONS = frozenset(
    {
        "records",
        "kpis",
        "filters",
        "variables",
        "activities",
        "actions",
        "anomalies",
        "eventLogs",
        "customObjects",
    }
)
_RECORD_COLLECTIONS = frozenset({"attributes", "newAttributes", "augmentedAttributes"})


class CaptureError(ValueError):
    """A source definition cannot be captured faithfully."""


class Source(BaseModel):
    """Non-secret provenance required to bind a capture to its source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str
    space_id: str
    package_id: str
    key: str
    mode: Literal["draft", "published"]

    @field_validator("tenant_id", "space_id", "package_id", "key")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Source identifiers must not be empty.")
        return value


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _normalize(value: Any, path: tuple[str, ...] = ()) -> Any:
    location = "/" + "/".join(path)
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise CaptureError(f"{location}: definition keys must be strings.")
        return {
            key: _normalize(item, (*path, key)) for key, item in sorted(value.items())
        }
    if isinstance(value, list):
        result = [
            _normalize(item, (*path, str(index))) for index, item in enumerate(value)
        ]
        keyed = (
            len(path) == 1
            and path[0] in _ROOT_COLLECTIONS
            or len(path) == 3
            and path[0] == "records"
            and path[2] in _RECORD_COLLECTIONS
        )
        if keyed:
            ids = [item.get("id") for item in result if isinstance(item, dict)]
            present = [item for item in ids if isinstance(item, str) and item]
            if len(present) != len(set(present)):
                raise CaptureError(f"{location}: duplicate source IDs.")
            # Missing IDs and null entries survive exactly; structural paths
            # remain meaningful by retaining their original order.
            # Record attribute order defines whole-record query column order.
            if len(path) == 1 and len(present) == len(result):
                result.sort(key=lambda item: item["id"])
        return result
    if value is None or type(value) in (str, bool, int, float):
        return value
    raise CaptureError(
        f"{location}: unsupported definition value {type(value).__name__}."
    )


class Capture(BaseModel):
    """Immutable canonical source content; no client or live object is retained."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    format_version: Literal[1] = FORMAT_VERSION
    source: Source
    definition_json: str
    input_variables_json: str | None = None
    joins_json: str | None = None
    """Data Model foreign keys as ``{"one", "many", "columns": [[one, many]]}``."""
    tables_json: str | None = None
    """Data Model tables by PQL name: ``{"primary_key": [...], "columns": {name: TYPE}}``."""
    validation_json: str | None = None
    """Calculated attributes rejected at pull: ``{record_id: {attribute_id: reason}}``."""
    types_json: str | None = None
    """Result types reported by Celonis, keyed by the resolved PQL expression."""

    @model_validator(mode="before")
    @classmethod
    def decode_sidecar(cls, value: Any) -> Any:
        if isinstance(value, dict) and "definition" in value:
            if "definition_json" in value:
                raise ValueError("Capture must contain one canonical definition.")
            value = dict(value)
            value["definition_json"] = json.dumps(
                value.pop("definition"), ensure_ascii=False, allow_nan=False
            )
        if isinstance(value, dict) and "input_variables" in value:
            if "input_variables_json" in value:
                raise ValueError("Capture must contain one input-variable snapshot.")
            value = dict(value)
            value["input_variables_json"] = json.dumps(
                value.pop("input_variables"), ensure_ascii=False, allow_nan=False
            )
        if isinstance(value, dict) and "joins" in value:
            if "joins_json" in value:
                raise ValueError("Capture must contain one join snapshot.")
            value = dict(value)
            value["joins_json"] = json.dumps(value.pop("joins"), ensure_ascii=False)
        for name in ("tables", "validation", "types"):
            if isinstance(value, dict) and name in value:
                if f"{name}_json" in value:
                    raise ValueError(f"Capture must contain one {name} snapshot.")
                value = dict(value)
                value[f"{name}_json"] = json.dumps(value.pop(name), ensure_ascii=False)
        return value

    @field_validator("tables_json", "validation_json", "types_json")
    @classmethod
    def canonical_mapping(cls, value: str | None) -> str | None:
        if value is None:
            return None
        payload = json.loads(value)
        if not isinstance(payload, dict):
            raise ValueError("Data Model snapshots must be JSON objects.")
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @field_validator("joins_json")
    @classmethod
    def canonical_joins(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            joins = [
                {
                    "one": str(item["one"]),
                    "many": str(item["many"]),
                    "columns": [[str(one), str(many)] for one, many in item["columns"]],
                }
                for item in json.loads(value)
            ]
        except (TypeError, ValueError, KeyError) as exc:
            raise ValueError(f"Invalid Data Model joins: {exc}") from exc
        joins.sort(key=lambda item: (item["one"], item["many"], item["columns"]))
        return json.dumps(joins, ensure_ascii=False, separators=(",", ":"))

    @field_validator("input_variables_json")
    @classmethod
    def canonical_inputs(cls, value: str | None) -> str | None:
        return None if value is None else cls.canonical_definition(value)

    @field_validator("definition_json")
    @classmethod
    def canonical_definition(cls, value: str) -> str:
        try:
            payload = json.loads(value)
            if not isinstance(payload, dict):
                raise CaptureError("KM definitions must be a JSON object.")
            return json.dumps(
                _normalize(payload),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid KM definition: {exc}") from exc

    @model_validator(mode="after")
    def matching_provenance(self) -> Capture:
        layer = self.to_dict()
        if layer.get("tenantId", self.source.tenant_id) != self.source.tenant_id:
            raise ValueError("KM tenantId does not match capture provenance.")
        metadata = layer.get("metadata")
        if (
            isinstance(metadata, dict)
            and metadata.get("key", self.source.key) != self.source.key
        ):
            raise ValueError("KM metadata.key does not match capture provenance.")
        return self

    @classmethod
    def create(
        cls,
        source: Source,
        definition: Mapping[str, Any],
        *,
        input_variables: Mapping[str, Any] | None = None,
        joins: Sequence[Mapping[str, Any]] | None = None,
        tables: Mapping[str, Any] | None = None,
        validation: Mapping[str, Mapping[str, str]] | None = None,
    ) -> Capture:
        """Detach from source state, preserving unknown fields and exact strings."""
        normalized = _normalize(definition)
        try:
            encoded = json.dumps(normalized, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise CaptureError(f"Invalid KM definition: {exc}") from exc
        tenant_id = normalized.get("tenantId")
        if tenant_id is not None and tenant_id != source.tenant_id:
            raise CaptureError("KM tenantId does not match capture provenance.")
        metadata = normalized.get("metadata")
        if isinstance(metadata, dict) and metadata.get("key", source.key) != source.key:
            raise CaptureError("KM metadata.key does not match capture provenance.")
        return cls(
            source=source,
            definition_json=encoded,
            input_variables_json=None
            if input_variables is None
            else json.dumps(
                _normalize(input_variables), ensure_ascii=False, allow_nan=False
            ),
            joins_json=None if joins is None else json.dumps(list(joins), ensure_ascii=False),
            tables_json=None if tables is None else json.dumps(dict(tables), ensure_ascii=False),
            validation_json=None
            if validation is None
            else json.dumps({k: dict(v) for k, v in validation.items()}, ensure_ascii=False),
        )

    def with_validation(self, validation: Mapping[str, Mapping[str, str]]) -> Capture:
        """A copy that records calculated attributes rejected at pull."""
        return Capture.model_validate(
            {
                **self.model_dump(),
                "validation_json": json.dumps(
                    {k: dict(v) for k, v in validation.items()}, ensure_ascii=False
                ),
            }
        )

    def with_types(self, types: Mapping[str, ValueType]) -> Capture:
        """Keep discovered types separate from the original KM definition."""
        return Capture.model_validate({**self.model_dump(), "types_json": json.dumps(dict(types))})

    @cached_property
    def types(self) -> Mapping[str, ValueType]:
        return _freeze(json.loads(self.types_json)) if self.types_json is not None else _freeze({})

    @cached_property
    def fingerprint(self) -> str:
        """Definition fingerprint, including record attribute order."""
        content = self.definition_json
        if self.input_variables_json is not None:
            content += "\n" + self.input_variables_json
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @cached_property
    def input_variables(self) -> Mapping[str, Any] | None:
        """Studio input definitions by key; None means an older, uncaptured source."""
        if self.input_variables_json is None:
            return None
        return _freeze(json.loads(self.input_variables_json))

    @cached_property
    def joins(self) -> tuple[Mapping[str, Any], ...] | None:
        """Data Model foreign keys; None when the capture has no join snapshot."""
        if self.joins_json is None:
            return None
        return tuple(_freeze(item) for item in json.loads(self.joins_json))

    @cached_property
    def tables(self) -> Mapping[str, Any] | None:
        """Data Model tables by PQL name, with primary key and column types."""
        return None if self.tables_json is None else _freeze(json.loads(self.tables_json))

    @cached_property
    def validation(self) -> Mapping[str, Mapping[str, str]]:
        """Calculated attributes rejected at pull, with the reason, by record ID."""
        return {} if self.validation_json is None else _freeze(json.loads(self.validation_json))

    @cached_property
    def definition(self) -> Mapping[str, Any]:
        """Deeply immutable definition metadata, including unknown fields."""
        return _freeze(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        """Return a detached JSON-compatible copy for execution or serialization."""
        return json.loads(self.definition_json)

    def to_json(self) -> str:
        """Readable, versioned sidecar with ordinary JSON definition fields."""
        return (
            json.dumps(
                {
                    "format_version": self.format_version,
                    "source": self.source.model_dump(),
                    "definition": self.to_dict(),
                    **(
                        {"input_variables": json.loads(self.input_variables_json)}
                        if self.input_variables_json is not None
                        else {}
                    ),
                    **(
                        {"joins": json.loads(self.joins_json)}
                        if self.joins_json is not None
                        else {}
                    ),
                    **{
                        name: json.loads(text)
                        for name, text in (
                            ("tables", self.tables_json),
                            ("validation", self.validation_json),
                            ("types", self.types_json),
                        )
                        if text is not None
                    },
                },
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )


_TABLE = re.compile(r'^\s*"?([A-Za-z_][\w$]*)"?\s*$')


def record_table(expression: Any) -> str | None:
    """The table a record reads when its expression is a plain table name."""
    match = _TABLE.match(expression) if isinstance(expression, str) else None
    return match.group(1) if match else None


Progress = Callable[[str, int, int], None]
"""Reports (task, completed, total) during slow pull steps."""


def data_model_tables(
    data_model: Any,
    *,
    only: Iterable[str] | None = None,
    progress: Progress | None = None,
    max_workers: int = 16,
) -> dict[str, dict[str, Any]]:
    """Tables of a native Data Model by PQL name, with primary key and column types.

    ``table.columns`` is a partial transport (every type reads STRING), so the
    column types come from ``get_columns()``: one request per table, which is
    slow, so requests run in parallel and ``only`` limits them to the tables
    the KM's records read (names compared case-insensitively).
    """
    # Imported here: generated packages import this module and stay light.
    from concurrent.futures import ThreadPoolExecutor, as_completed

    wanted = None if only is None else {name.lower() for name in only}
    tables = [
        table for table in data_model.get_tables()
        if wanted is None or (table.alias or table.name).lower() in wanted
    ]
    result: dict[str, dict[str, Any]] = {}
    if progress is not None:
        progress("Fetching Data Model columns", 0, len(tables))
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(tables)))) as executor:
        futures = {executor.submit(table.get_columns): table for table in tables}
        for done, future in enumerate(as_completed(futures), start=1):
            table = futures[future]
            result[table.alias or table.name] = {
                "primary_key": list(table.primary_keys or ()),
                "columns": {column.name: column.type_ for column in future.result()},
            }
            if progress is not None:
                progress(f"Fetching Data Model columns: {table.alias or table.name}", done, len(tables))
    return result


def data_model_joins(data_model: Any) -> list[dict[str, Any]]:
    """Foreign keys of a native Data Model, with tables named as PQL names them.

    A foreign key's source table is the "one" side and its target the "many"
    side; each column pair is (one column, many column).
    """
    tables = {
        table.id: table.alias or table.name for table in data_model.get_tables()
    }
    joins = []
    for key in data_model.get_foreign_keys():
        if key.source_table_id not in tables or key.target_table_id not in tables:
            raise CaptureError(f"Data Model foreign key {key.id} references an unknown table.")
        joins.append(
            {
                "one": tables[key.source_table_id],
                "many": tables[key.target_table_id],
                "columns": [
                    [column.source_column_name, column.target_column_name]
                    for column in key.columns or ()
                ],
            }
        )
    return joins


def retrieve(
    native: Any,
    *,
    space_id: str,
    package_id: str,
    mode: Literal["draft", "published"],
    data_model: Any = None,
    progress: Progress | None = None,
) -> Capture:
    """Read one final-layer response through the authenticated PyCelonis client.

    The endpoint and options mirror PyCelonis 2.15.1's get_content. Reading the
    raw JSON avoids lossy transport models and explicitly selects lifecycle.
    Studio input defaults are read separately from the matching node revision.
    These are metadata observations, not an atomic execution snapshot.
    """
    from urllib.parse import quote

    if mode not in ("draft", "published"):
        raise CaptureError("mode must be 'draft' or 'published'.")
    if not isinstance(native.root_with_key, str) or not native.root_with_key:
        raise CaptureError("KM has no root_with_key for effective-content retrieval.")
    response = native.client.request(
        method="POST",
        url=f"/semantic-layer/api/layer/{quote(native.root_with_key, safe='')}/final",
        params={"isDraft": mode == "draft"},
        json={
            "withVariableReplacement": False,
            "withAutogeneratedDataModelData": True,
            "withDefaultValues": True,
            "validatePql": True,
            "withUnknownVariablesValidation": True,
        },
        parse_json=True,
    )
    layer = response.get("layer") if isinstance(response, dict) else None
    if not isinstance(layer, dict):
        raise CaptureError("Effective KM response has no definition layer.")
    tenant_id = layer.get("tenantId")
    if not isinstance(tenant_id, str) or not tenant_id:
        raise CaptureError(
            "Effective KM response has no tenantId for source validation."
        )
    source = Source(
        tenant_id=tenant_id,
        space_id=space_id,
        package_id=package_id,
        key=native.key,
        mode=mode,
    )
    node_id = layer.get("nodeEntityId")
    if not isinstance(node_id, str) or not node_id:
        raise CaptureError(
            "Effective KM has no nodeEntityId for input-variable capture."
        )
    node_url = f"/package-manager/api/nodes/{quote(node_id, safe='')}"
    node = native.client.request(method="GET", url=node_url, parse_json=True)
    if not isinstance(node, dict):
        raise CaptureError("Studio response has no KM node metadata.")
    revision = node.get("workingDraftId" if mode == "draft" else "activatedDraftId")
    if not isinstance(revision, str) or not revision:
        raise CaptureError(
            f"KM node has no {mode} revision for input-variable capture."
        )
    if node.get("draftId") != revision:
        node = native.client.request(
            method="GET",
            url=node_url,
            params={"draftId": revision},
            parse_json=True,
        )
    if (
        not isinstance(node, dict)
        or node.get("draftId") != revision
        or node.get("key") != source.key
        or node.get("id") != node_id
    ):
        raise CaptureError(
            "Studio input-variable source does not match the selected KM revision."
        )
    definitions = node.get("inputVariableDefinitions")
    if not isinstance(definitions, list):
        raise CaptureError("Studio node has no inputVariableDefinitions list.")
    inputs = {}
    for item in definitions:
        key = item.get("key") if isinstance(item, dict) else None
        if not isinstance(key, str) or not key or key in inputs:
            raise CaptureError("Studio input variables have missing or duplicate keys.")
        inputs[key] = item
    if data_model is None:
        return Capture.create(source, layer, input_variables=inputs)
    return Capture.create(
        source,
        layer,
        input_variables=inputs,
        joins=data_model_joins(data_model),
        tables=data_model_tables(
            data_model,
            only={
                table
                for record in layer.get("records") or ()
                if isinstance(record, dict)
                for table in [record_table(record.get("pql"))]
                if table is not None
            },
            progress=progress,
        ),
    )
