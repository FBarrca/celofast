"""Typed handles for variable-backed input components in Studio Views."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from pycelonis.ems.apps.content_node.view.component import Component

from celofast.exceptions import ComponentVariableError, ResourceResolutionError

if TYPE_CHECKING:
    from celofast.resources.view import ViewHandle


_VARIABLE_PATTERN = re.compile(r"^\$\{([^{}]+)\}$")


def _enum_value(value: object) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)


@dataclass(frozen=True)
class InputVariableValue:
    """One KM input-variable definition combined with its current value."""

    key: str
    data_type: str | None
    default_value: str | None
    assigned_value: str | None
    value: str | None
    display_name: str | None = None
    description: str | None = None
    scope: str | None = None
    propagate: bool | None = None

    @property
    def uses_default(self) -> bool:
        """Whether the effective value falls back to the configured default."""

        return self.assigned_value is None


@dataclass(frozen=True)
class DropdownOption:
    """One value offered by a data-backed dropdown or selector."""

    value: object
    label: str


@dataclass(frozen=True)
class DateRange:
    """The effective start and end dates of a range date picker."""

    start: date | None
    end: date | None


class ViewInputValueClient:
    """Read current KM input values through the Package Manager API."""

    def __init__(self, view: ViewHandle) -> None:
        self._view = view

    def find_all(self) -> Mapping[str, InputVariableValue]:
        km = self._view.km.native
        client = getattr(km, "client", None)
        if client is None:
            raise ResourceResolutionError(
                "The native Knowledge Model does not expose its API client."
            )

        response = client.request(
            method="GET",
            url=(
                f"/package-manager/api/nodes/{self._view.native.id}"
                "/input-variables/values"
            ),
            params={
                "refNodeId": km.id,
                "appMode": "CREATOR"
                if self._view.km.mode == "draft"
                else "VIEWER",
            },
            parse_json=True,
            type_=Any,
        )
        if response is None:
            return {}
        if not isinstance(response, list):
            raise ResourceResolutionError(
                "Package Manager returned an invalid input-variable response."
            )

        definitions = self._view._input_definitions_by_key
        values: dict[str, InputVariableValue] = {}
        for raw in response:
            if hasattr(raw, "json_dict"):
                raw = raw.json_dict(by_alias=True)
            if not isinstance(raw, Mapping):
                raise ResourceResolutionError(
                    "Package Manager returned an invalid input-variable entry."
                )
            key = raw.get("key")
            if not isinstance(key, str) or not key:
                raise ResourceResolutionError(
                    "Package Manager returned an input variable without a key."
                )
            definition = definitions.get(key)
            default = raw.get("defaultValue")
            if default is None and definition is not None:
                default = getattr(definition, "default_value", None)
            assigned = raw.get("value")
            effective = raw.get("valueOrDefault")
            if effective is None:
                effective = assigned if assigned is not None else default
            values[key] = InputVariableValue(
                key=key,
                data_type=_enum_value(
                    raw.get("dataType")
                    or (getattr(definition, "data_type", None) if definition else None)
                ),
                default_value=default,
                assigned_value=assigned,
                value=effective,
                display_name=raw.get("displayName")
                or (getattr(definition, "display_name", None) if definition else None),
                description=raw.get("description")
                or (getattr(definition, "description", None) if definition else None),
                scope=_enum_value(
                    raw.get("scope")
                    or (getattr(definition, "scope", None) if definition else None)
                ),
                propagate=raw.get("propagate")
                if "propagate" in raw
                else (getattr(definition, "propagate", None) if definition else None),
            )
        return values


class ViewInputHandle:
    """Common metadata and value resolution for a typed View input."""

    COMPONENT_TYPES: tuple[str, ...] = ()

    def __init__(
        self,
        view: ViewHandle,
        component: Component,
        *,
        tab_name: str | None,
    ) -> None:
        self._view = view
        self._component = component
        self._tab_name = tab_name
        self._variable_keys = self._extract_variable_keys()

    def _validate_variable_keys(self, keys: tuple[str, ...]) -> None:
        if len(keys) != 1:
            raise ComponentVariableError(
                f"{self._component.type_!r} component {self._component.id!r} "
                "must bind exactly "
                "one Knowledge Model input variable."
            )

    @property
    def id(self) -> str:
        return self._component.id

    @property
    def name(self) -> str:
        name = getattr(self._component.settings, "name", None)
        return name if isinstance(name, str) and name else self.id

    @property
    def tab_name(self) -> str | None:
        return self._tab_name

    @property
    def component(self) -> Component:
        """Return the native PyCelonis component as an escape hatch."""

        return self._component

    @property
    def settings(self) -> Mapping[str, object]:
        """Return the component's serialized settings as a read-only mapping."""

        from types import MappingProxyType

        return MappingProxyType(dict(self._settings()))

    @property
    def variable_key(self) -> str:
        self._validate_variable_keys(self._variable_keys)
        return self._variable_keys[0]

    @property
    def variable_keys(self) -> tuple[str, ...]:
        return self._variable_keys

    @property
    def variable_definition(self) -> object:
        self._ensure_defined_variables()
        return self._view._input_definitions_by_key[self.variable_key]

    def validate_binding(self) -> None:
        """Validate this component's binding against its Knowledge Model."""

        self._ensure_defined_variables()

    @property
    def data_type(self) -> str | None:
        return _enum_value(getattr(self.variable_definition, "data_type", None))

    @property
    def default_value(self) -> str | None:
        return getattr(self.variable_definition, "default_value", None)

    @property
    def scope(self) -> str | None:
        return _enum_value(getattr(self.variable_definition, "scope", None))

    @property
    def variable_display_name(self) -> str | None:
        return getattr(self.variable_definition, "display_name", None)

    @property
    def description(self) -> str | None:
        return getattr(self.variable_definition, "description", None)

    @property
    def propagate(self) -> bool | None:
        return getattr(self.variable_definition, "propagate", None)

    def get(self) -> object:
        """Fetch and decode this component's current effective value."""

        return self._decode(self.details().value)

    def details(self) -> InputVariableValue:
        """Fetch the complete definition and value record for this input."""

        self._ensure_defined_variables()
        values = self._view._input_value_client.find_all()
        try:
            return values[self.variable_key]
        except KeyError as exc:
            raise ResourceResolutionError(
                f"Package Manager did not return input variable "
                f"{self.variable_key!r}."
            ) from exc

    def _settings(self) -> Mapping[str, object]:
        return self._component.settings.dict(by_alias=True)

    def _ensure_defined_variables(self) -> None:
        self._validate_variable_keys(self.variable_keys)
        definitions = self._view._input_definitions_by_key
        for key in self.variable_keys:
            if key not in definitions:
                raise ComponentVariableError(
                    f"{self._component.type_!r} component {self.id!r} references "
                    f"{key!r}, but that variable is not defined by Knowledge "
                    f"Model {self._view.km.native.key!r}."
                )

    def _extract_variable_keys(self) -> tuple[str, ...]:
        settings = self._settings()
        on_change = settings.get("onChange")
        update = on_change.get("update") if isinstance(on_change, Mapping) else None
        variables = update.get("variables") if isinstance(update, Mapping) else None
        keys: list[str] = []
        if isinstance(variables, list):
            for variable in variables:
                if isinstance(variable, Mapping):
                    name = variable.get("name")
                    if isinstance(name, str) and name:
                        keys.append(name)
        elif isinstance(variables, Mapping):
            keys.extend(
                name
                for name in variables.values()
                if isinstance(name, str) and name
            )

        if not keys:
            configured_value = settings.get("value")
            if isinstance(configured_value, str):
                match = _VARIABLE_PATTERN.match(configured_value)
                if match:
                    keys.append(match.group(1))
        return tuple(dict.fromkeys(keys))

    def _decode(self, value: str | None) -> object:
        return value


class InputBoxHandle(ViewInputHandle):
    """A variable-backed Studio ``input-box`` component."""

    COMPONENT_TYPES = ("input-box",)

    @property
    def input_type(self) -> str | None:
        value = self._settings().get("type")
        return value if isinstance(value, str) else None

    @property
    def placeholder(self) -> str | None:
        value = self._settings().get("placeholder")
        return value if isinstance(value, str) else None


class DropdownHandle(ViewInputHandle):
    """A variable-backed, data-backed Studio dropdown component."""

    COMPONENT_TYPES = ("input-dropdown",)

    @property
    def selection_mode(self) -> str:
        on_change = self._settings().get("onChange")
        update = on_change.get("update") if isinstance(on_change, Mapping) else None
        selection = update.get("selection") if isinstance(update, Mapping) else None
        return selection if isinstance(selection, str) else "single"

    @property
    def attribute(self) -> str | None:
        value = self._settings().get("attribute")
        return value if isinstance(value, str) else None

    @property
    def data_source_id(self) -> str | None:
        return self._attribute_parts()[0]

    @property
    def attribute_id(self) -> str | None:
        return self._attribute_parts()[1]

    @property
    def attribute_pql(self) -> str | None:
        try:
            return self._option_query()[0]
        except ResourceResolutionError:
            return None

    def options(
        self,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[DropdownOption, ...]:
        """Query the configured KM attribute for distinct dropdown options."""

        self._ensure_defined_variables()
        pql, filters = self._option_query()
        frame = self._view.km.execute(
            {"columns": {"value": pql}, "filters": filters},
            limit=limit,
            offset=offset,
            distinct=True,
        )
        return tuple(
            DropdownOption(value=value, label=str(value))
            for value in frame["value"].tolist()
            if not _is_missing(value)
        )

    def _decode(self, value: str | None) -> object:
        if self.selection_mode == "multiple":
            return decode_multiple_value(value)
        return value

    def _option_query(self) -> tuple[str, list[str]]:
        source_id, attribute_id = self._attribute_parts()
        if source_id is None or attribute_id is None:
            raise ResourceResolutionError(
                f"Dropdown {self.id!r} has no valid configured attribute."
            )
        for source in self._component.settings.data_sources:
            if source.id != source_id:
                continue
            for attribute in source.attributes:
                if attribute.id == attribute_id:
                    return attribute.pql, [item.to_pql().query for item in source.filters]
        raise ResourceResolutionError(
            f"Dropdown {self.id!r} references unknown attribute {self.attribute!r}."
        )

    def _attribute_parts(self) -> tuple[str | None, str | None]:
        attribute_ref = self.attribute
        if not attribute_ref or "." not in attribute_ref:
            return None, None
        source_id, attribute_id = attribute_ref.split(".", 1)
        return source_id, attribute_id


class SelectorHandle(DropdownHandle):
    """A variable-backed selector with queryable options."""

    COMPONENT_TYPES = ("input-selector", "selector")


class DatePickerHandle(ViewInputHandle):
    """A variable-backed date picker returning ``datetime.date`` values."""

    COMPONENT_TYPES = ("input-date-picker", "date-picker")

    @property
    def range_selection(self) -> bool:
        return self._settings().get("rangeSelection") is True

    @property
    def variable_key(self) -> str:
        if self.range_selection:
            raise ComponentVariableError(
                f"Date picker {self.id!r} is a range; use start_variable_key "
                "and end_variable_key."
            )
        return super().variable_key

    @property
    def start_variable_key(self) -> str | None:
        variables = self._configured_variables()
        value = variables.get("startDate")
        return value if isinstance(value, str) else None

    @property
    def end_variable_key(self) -> str | None:
        variables = self._configured_variables()
        value = variables.get("endDate")
        return value if isinstance(value, str) else None

    @property
    def minimum_date(self) -> str | None:
        value = self._settings().get("minDate")
        return value if isinstance(value, str) else None

    @property
    def maximum_date(self) -> str | None:
        value = self._settings().get("maxDate")
        return value if isinstance(value, str) else None

    def get(self) -> date | DateRange | None:
        self._ensure_defined_variables()
        values = self._view._input_value_client.find_all()
        if self.range_selection:
            return DateRange(
                start=self._decode_key(values, self.start_variable_key),
                end=self._decode_key(values, self.end_variable_key),
            )
        return self._decode_key(values, self.variable_key)

    def _validate_variable_keys(self, keys: tuple[str, ...]) -> None:
        expected = 2 if self.range_selection else 1
        if len(keys) != expected:
            raise ComponentVariableError(
                f"Date picker {self._component.id!r} must bind exactly "
                f"{expected} Knowledge Model input variable"
                f"{'s' if expected != 1 else ''}."
            )

    def _configured_variables(self) -> Mapping[str, object]:
        on_change = self._settings().get("onChange")
        update = on_change.get("update") if isinstance(on_change, Mapping) else None
        variables = update.get("variables") if isinstance(update, Mapping) else None
        return variables if isinstance(variables, Mapping) else {}

    def _decode_key(
        self,
        values: Mapping[str, InputVariableValue],
        key: str | None,
    ) -> date | None:
        if key is None or key not in values:
            raise ResourceResolutionError(
                f"Package Manager did not return date-picker variable {key!r}."
            )
        return self._decode(values[key].value)

    def _decode(self, value: str | None) -> date | None:
        if value is None:
            return None
        candidate = value.strip().strip('"').strip("'")
        try:
            return date.fromisoformat(candidate)
        except ValueError as exc:
            raise ResourceResolutionError(
                f"Date picker {self.id!r} returned non-ISO date {value!r}."
            ) from exc


class CheckboxHandle(ViewInputHandle):
    """A variable-backed checkbox returning a boolean value."""

    COMPONENT_TYPES = ("input-checkbox", "checkbox")

    def _decode(self, value: str | None) -> bool | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
        raise ResourceResolutionError(
            f"Checkbox {self.id!r} returned invalid boolean {value!r}."
        )


def _is_missing(value: object) -> bool:
    """Return whether a scalar option is null without failing on arrays."""

    try:
        import pandas as pd

        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def decode_multiple_value(value: str | None) -> tuple[object, ...]:
    """Decode a JSON-list KM value while preserving non-JSON scalar strings."""

    if value is None:
        return ()
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return (value,)
    return tuple(decoded) if isinstance(decoded, list) else (decoded,)
