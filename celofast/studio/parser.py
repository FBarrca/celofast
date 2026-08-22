"""Parse published Celonis Studio View JSON without depending on PyCelonis internals."""

import json
from typing import Any, Dict, Mapping

from .exceptions import TableNotFoundError, ViewFormatError
from .models import ViewColumn, ViewFilter, ViewTable


def load_serialized_content(view: Any) -> Dict[str, Any]:
    """Return a View's ``serialized_content`` as a dictionary.

    PyCelonis versions expose this either as an object attribute or through
    ``json_dict()``. Supporting both keeps the parser easy to mock and portable
    across projects.
    """

    raw = None
    if hasattr(view, "json_dict"):
        payload = view.json_dict()
        if isinstance(payload, Mapping):
            raw = payload.get("serialized_content", payload.get("serializedContent"))

    if raw is None:
        raw = getattr(view, "serialized_content", None)

    if isinstance(raw, Mapping):
        return dict(raw)
    if not isinstance(raw, str) or not raw.strip():
        raise ViewFormatError("The View does not expose published serialized_content.")

    try:
        content = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ViewFormatError("The View's serialized_content is not valid JSON.") from exc

    if not isinstance(content, dict):
        raise ViewFormatError("The View's serialized_content must decode to an object.")
    return content


class ViewTableParser:
    """Extract table definitions from a published Studio View."""

    def __init__(self, view: Any):
        self._content = load_serialized_content(view)

    def table(self, table_name: str) -> ViewTable:
        components = self._content.get("components")
        if not isinstance(components, list):
            raise ViewFormatError("The published View does not contain a components list.")

        requested_name = table_name.strip()
        for component in components:
            settings = component.get("settings", {}) if isinstance(component, Mapping) else {}
            name = str(settings.get("name", "")).strip()
            if component.get("type") == "table" and name == requested_name:
                return self._parse_table(settings, requested_name)

        raise TableNotFoundError(
            "Table component {!r} was not found in the published View.".format(requested_name)
        )

    @staticmethod
    def _parse_table(settings: Mapping[str, Any], table_name: str) -> ViewTable:
        data_sources = settings.get("dataSources")
        if not isinstance(data_sources, list) or not data_sources:
            raise ViewFormatError(
                "Table {!r} has no configured data source.".format(table_name)
            )

        source = data_sources[0]
        if not isinstance(source, Mapping):
            raise ViewFormatError(
                "Table {!r} has an invalid data source.".format(table_name)
            )

        raw_columns = source.get("attributes")
        if not isinstance(raw_columns, list):
            raise ViewFormatError(
                "Table {!r} has no attributes list.".format(table_name)
            )

        columns = []
        for raw_column in raw_columns:
            if not isinstance(raw_column, Mapping):
                raise ViewFormatError(
                    "Table {!r} contains an invalid column definition.".format(table_name)
                )
            referenced = raw_column.get("referencedEntity") or {}
            name = raw_column.get("displayName") or referenced.get("id")
            pql = raw_column.get("pql")
            if not name or not isinstance(pql, str) or not pql.strip():
                raise ViewFormatError(
                    "Every column in table {!r} needs a name and PQL expression.".format(
                        table_name
                    )
                )
            columns.append(
                ViewColumn(
                    name=str(name).strip(),
                    pql=pql,
                    hidden=bool(raw_column.get("hide", False)),
                    referenced_entity=dict(referenced),
                )
            )

        raw_filters = source.get("filters", [])
        if not isinstance(raw_filters, list):
            raise ViewFormatError(
                "Table {!r} has an invalid filters value.".format(table_name)
            )

        filters = []
        for raw_filter in raw_filters:
            if not isinstance(raw_filter, Mapping) or not isinstance(raw_filter.get("pql"), str):
                raise ViewFormatError(
                    "Table {!r} contains an invalid filter definition.".format(table_name)
                )
            filters.append(
                ViewFilter(
                    pql=raw_filter["pql"],
                    is_referenced=bool(raw_filter.get("isReferenced", False)),
                )
            )

        return ViewTable(table_name, tuple(columns), tuple(filters))
