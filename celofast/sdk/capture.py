"""Offline snapshots of a Knowledge Model and the Data Model it reads.

A ``Capture`` is the only input to generation: the KM's effective definition,
its Studio input defaults, the Data Model's tables and foreign keys, and what
pull learned by test-running calculated attributes (result types and
rejections). ``retrieve`` reads it through an authenticated PyCelonis client.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from celofast.sdk.hydration import ValueType


class CaptureError(ValueError):
    """A source definition cannot be captured or generated faithfully."""


class Source(BaseModel):
    """Non-secret identity of the Knowledge Model a capture was read from."""

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


class Capture(BaseModel):
    """Everything generation needs, as plain JSON-compatible data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    format_version: Literal[1] = 1
    source: Source
    definition: dict[str, Any]
    """The KM's effective (final-layer) definition, as Celonis returns it."""
    input_variables: dict[str, Any] | None = None
    """Studio input definitions by key, including their default values."""
    joins: list[dict[str, Any]] | None = None
    """Data Model foreign keys: ``{"one", "many", "columns": [[one, many]]}``."""
    tables: dict[str, Any] | None = None
    """Data Model tables by PQL name: ``{"primary_key": [...], "columns": {name: TYPE}}``."""
    validation: dict[str, dict[str, str]] = {}
    """Calculated attributes rejected at pull: ``{record_id: {attribute_id: reason}}``."""
    types: dict[str, ValueType] = {}
    """Result types reported by Celonis, keyed by the resolved PQL expression."""


_TABLE = re.compile(r'^\s*"?([A-Za-z_][\w$]*)"?\s*$')


def record_table(expression: Any) -> str | None:
    """The table a record reads when its expression is a plain table name."""
    match = _TABLE.match(expression) if isinstance(expression, str) else None
    return match.group(1) if match else None


Progress = Callable[[str, int, int], None]
"""Reports (task, completed, total) during slow pull steps."""


def data_model_tables(
    data_model: Any, *, only: Iterable[str], progress: Progress | None = None
) -> dict[str, dict[str, Any]]:
    """Primary keys and column types of the named tables (case-insensitive).

    ``table.columns`` reads every type as STRING, so types come from
    ``get_columns()``: one slow request per table, run in parallel.
    """
    # Imported here: generated packages import this module and stay light.
    from concurrent.futures import ThreadPoolExecutor, as_completed

    wanted = {name.lower() for name in only}
    tables = [t for t in data_model.get_tables() if (t.alias or t.name).lower() in wanted]
    result: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(16, len(tables)))) as executor:
        futures = {executor.submit(table.get_columns): table for table in tables}
        for done, future in enumerate(as_completed(futures), start=1):
            table = futures[future]
            name = table.alias or table.name
            result[name] = {
                "primary_key": list(table.primary_keys or ()),
                "columns": {column.name: column.type_ for column in future.result()},
            }
            if progress is not None:
                progress(f"Fetching Data Model columns: {name}", done, len(tables))
    return result


def data_model_joins(data_model: Any) -> list[dict[str, Any]]:
    """Foreign keys with tables named as PQL names them.

    A foreign key's source table is the "one" side and its target the "many"
    side; each column pair is (one column, many column).
    """
    names = {table.id: table.alias or table.name for table in data_model.get_tables()}
    joins = []
    for key in data_model.get_foreign_keys():
        if key.source_table_id not in names or key.target_table_id not in names:
            raise CaptureError(f"Data Model foreign key {key.id} references an unknown table.")
        joins.append({
            "one": names[key.source_table_id],
            "many": names[key.target_table_id],
            "columns": [[c.source_column_name, c.target_column_name] for c in key.columns or ()],
        })
    return joins


def _input_variables(native: Any, node_id: str, key: str, mode: str) -> dict[str, Any]:
    """Studio input definitions of the KM revision that matches ``mode``."""
    from urllib.parse import quote

    url = f"/package-manager/api/nodes/{quote(node_id, safe='')}"
    node = native.client.request(method="GET", url=url, parse_json=True)
    if not isinstance(node, dict):
        raise CaptureError("Studio response has no KM node metadata.")
    revision = node.get("workingDraftId" if mode == "draft" else "activatedDraftId")
    if not isinstance(revision, str) or not revision:
        raise CaptureError(f"KM node has no {mode} revision for input-variable capture.")
    if node.get("draftId") != revision:
        node = native.client.request(
            method="GET", url=url, params={"draftId": revision}, parse_json=True
        )
    if not isinstance(node, dict) or (node.get("draftId"), node.get("key")) != (revision, key):
        raise CaptureError("Studio input-variable source does not match the selected KM revision.")
    inputs: dict[str, Any] = {}
    for item in node.get("inputVariableDefinitions") or ():
        name = item.get("key") if isinstance(item, dict) else None
        if not isinstance(name, str) or not name or name in inputs:
            raise CaptureError("Studio input variables have missing or duplicate keys.")
        inputs[name] = item
    return inputs


def retrieve(
    native: Any,
    *,
    space_id: str,
    package_id: str,
    mode: Literal["draft", "published"],
    data_model: Any = None,
    progress: Progress | None = None,
) -> Capture:
    """Read the KM's final layer, input defaults, and (optionally) Data Model.

    The endpoint and options mirror PyCelonis 2.15.1's ``get_content``; reading
    the raw JSON avoids lossy transport models and selects the lifecycle
    explicitly.
    """
    from urllib.parse import quote

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
    tenant_id, node_id = layer.get("tenantId"), layer.get("nodeEntityId")
    if not isinstance(tenant_id, str) or not tenant_id:
        raise CaptureError("Effective KM response has no tenantId.")
    if not isinstance(node_id, str) or not node_id:
        raise CaptureError("Effective KM has no nodeEntityId for input-variable capture.")
    source = Source(
        tenant_id=tenant_id, space_id=space_id, package_id=package_id, key=native.key, mode=mode
    )
    capture = Capture(
        source=source,
        definition=layer,
        input_variables=_input_variables(native, node_id, native.key, mode),
    )
    if data_model is None:
        return capture
    read = {
        table for record in layer.get("records") or ()
        if isinstance(record, dict) and (table := record_table(record.get("pql")))
    }
    return capture.model_copy(update={
        "joins": data_model_joins(data_model),
        "tables": data_model_tables(data_model, only=read, progress=progress),
    })
