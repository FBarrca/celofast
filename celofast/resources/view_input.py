"""View inputs (input boxes, dropdowns, selectors, date pickers, checkboxes).

Each input is bound to KM or View-scoped input variables. Reading ``.value``
or ``.details()`` fetches the current values from Celonis every time; inputs
are read-only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import cached_property
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import pandas as pd
import pycelonis.pql as pql
from pycelonis.ems.apps.content_node.view.component import Component

from celofast.exceptions import ComponentVariableError, ResourceResolutionError

if TYPE_CHECKING:
    from celofast.resources.view import ViewHandle

_PLACEHOLDER = re.compile(r"^\$\{([^{}]+)\}$")


def _text(value: object) -> str | None:
    """A string, the value of an enum, or None."""
    if value is None:
        return None
    return str(getattr(value, "value", value))


@dataclass(frozen=True)
class InputVariableValue:
    """One input variable's definition together with its current value."""

    key: str
    data_type: str | None
    default_value: str | None
    assigned_value: str | None
    value: str | None
    """The effective value: the assigned value, otherwise the default."""
    display_name: str | None = None
    description: str | None = None
    scope: str | None = None
    propagate: bool | None = None

    @property
    def uses_default(self) -> bool:
        """Whether no value is assigned, so the default applies."""
        return self.assigned_value is None

    @classmethod
    def of(cls, variable: Any, definition: Any = None) -> InputVariableValue:
        """Combine a value read from Celonis with the variable's definition."""
        def field(name: str) -> Any:
            value = getattr(variable, name, None)
            return getattr(definition, name, None) if value is None else value

        assigned, default = variable.value, field("default_value")
        effective = variable.value_or_default
        if effective is None:
            effective = assigned if assigned is not None else default
        propagate = field("propagate")
        return cls(
            key=variable.key,
            data_type=_text(field("data_type")),
            default_value=_text(default),
            assigned_value=_text(assigned),
            value=_text(effective),
            display_name=_text(field("display_name")),
            description=_text(field("description")),
            scope=_text(field("scope")),
            propagate=propagate if isinstance(propagate, bool) else None,
        )


@dataclass(frozen=True)
class DropdownOption:
    """One value offered by a dropdown or selector."""

    value: object
    label: str


@dataclass(frozen=True)
class DateRange:
    """The start and end dates of a range date picker."""

    start: date | None
    end: date | None


@dataclass(frozen=True)
class DateRangeDetails:
    """The current records of both ends of a range date picker."""

    start: InputVariableValue
    end: InputVariableValue


def _update(settings: Mapping[str, object], event: str = "onChange") -> Mapping[str, object]:
    """The ``<event>.update`` settings of a component or item, or an empty mapping."""
    handler = settings.get(event)
    update = handler.get("update") if isinstance(handler, Mapping) else None
    return update if isinstance(update, Mapping) else {}


def _bound_names(variables: object) -> list[str]:
    """Variable names from ``[{"name": ...}]`` or ``{role: name}`` settings."""
    if isinstance(variables, Mapping):
        names: list[object] = list(variables.values())
    elif isinstance(variables, list):
        names = [item.get("name") for item in variables if isinstance(item, Mapping)]
    else:
        names = []
    return [name for name in names if isinstance(name, str) and name]


class ViewElement:
    """A table or input of a View, found with ``view[selector]``."""

    def __init__(self, view: ViewHandle, component: Component, *, tab_name: str | None) -> None:
        self._view = view
        self._component = component
        self._tab_name = tab_name

    @property
    def id(self) -> str:
        """The component ID; unique within the View."""
        return self._component.id

    @property
    def name(self) -> str:
        """The configured display name, or the ID when none is set."""
        name = getattr(self._component.settings, "name", None)
        return name if isinstance(name, str) and name else self.id

    @property
    def tab_name(self) -> str | None:
        """The containing tab's name, or None at the View's root."""
        return self._tab_name

    @property
    def component(self) -> Component:
        """The native PyCelonis component."""
        return self._component


class ViewInputHandle(ViewElement):
    """An input bound to one input variable."""

    @cached_property
    def settings(self) -> Mapping[str, object]:
        """The component's settings, as configured in Studio."""
        return MappingProxyType(self._component.settings.dict(by_alias=True))

    @cached_property
    def variable_keys(self) -> tuple[str, ...]:
        """Every input variable the component updates, primary first."""
        keys = _bound_names(_update(self.settings).get("variables"))
        value = self.settings.get("value")
        if not keys and isinstance(value, str):
            match = _PLACEHOLDER.match(value)
            keys = [match.group(1)] if match else []
        if not keys:
            keys = _bound_names(self.settings.get("variables"))
        return tuple(dict.fromkeys(keys))

    @property
    def variable_key(self) -> str:
        """The input variable holding the component's value."""
        self._check_key_count(len(self.variable_keys))
        return self.variable_keys[0]

    @property
    def variable_definition(self) -> object:
        """The native definition of :attr:`variable_key`."""
        self._check_binding()
        return self._view.input_definitions[self.variable_key]

    @property
    def value(self) -> object:
        """The current value, read now and decoded for this kind of input."""
        details = self.details()
        assert isinstance(details, InputVariableValue)
        return self._decode(details.value)

    def details(self) -> InputVariableValue | DateRangeDetails:
        """The variable's definition and current value, read now."""
        self._check_binding()
        return self._read(self._view._input_values(), self.variable_key)

    def _read(self, values: Mapping[str, InputVariableValue], key: str | None) -> InputVariableValue:
        if key is None or key not in values:
            raise ResourceResolutionError(f"Celonis returned no value for input variable {key!r}.")
        return values[key]

    def _check_key_count(self, count: int) -> None:
        if count != 1:
            raise self._binding_error("must bind exactly one input variable")

    def _binding_error(self, problem: str) -> ComponentVariableError:
        return ComponentVariableError(f"{self._component.type_!r} component {self.id!r} {problem}.")

    def _check_binding(self) -> None:
        """Every bound variable must be defined by the KM or the View."""
        self._check_key_count(len(self.variable_keys))
        for key in self.variable_keys:
            if key not in self._view.input_definitions:
                raise self._binding_error(
                    f"references {key!r}, but that variable is not defined by Knowledge "
                    f"Model {self._view.native_km.key!r} or the View"
                )

    def _decode(self, value: str | None) -> object:
        return value


class InputBoxHandle(ViewInputHandle):
    """An input box; its value is a string."""

    @property
    def input_type(self) -> str | None:
        value = self.settings.get("type")
        return value if isinstance(value, str) else None

    @property
    def placeholder(self) -> str | None:
        value = self.settings.get("placeholder")
        return value if isinstance(value, str) else None


class DropdownHandle(ViewInputHandle):
    """A dropdown; its value is a string, or a tuple for multiple selection.

    A manually configured dropdown may also update companion variables; its
    selected value is the first bound variable.
    """

    @property
    def selection_mode(self) -> str:
        selection = _update(self.settings).get("selection")
        return selection if isinstance(selection, str) else "single"

    @property
    def attribute(self) -> str | None:
        """The configured ``<data source ID>.<attribute ID>`` of a data-backed dropdown."""
        value = self.settings.get("attribute")
        return value if isinstance(value, str) and "." in value else None

    @property
    def data_source_id(self) -> str | None:
        return self.attribute.split(".", 1)[0] if self.attribute else None

    @property
    def attribute_id(self) -> str | None:
        return self.attribute.split(".", 1)[1] if self.attribute else None

    @property
    def attribute_pql(self) -> str | None:
        """The PQL expression of the configured attribute, if it exists."""
        found = self._attribute_query()
        return found[0] if found else None

    def options(self, *, limit: int | None = None, offset: int | None = None) -> tuple[DropdownOption, ...]:
        """The configured items, or the distinct values of the configured attribute."""
        self._check_binding()
        if self.attribute is None:
            start = offset or 0
            items = self._manual_options()
            return items[start: None if limit is None else start + limit]
        found = self._attribute_query()
        if found is None:
            raise ResourceResolutionError(f"Dropdown {self.id!r} references unknown attribute {self.attribute!r}.")
        expression, filters = found
        bind = self._view._binder()
        query = pql.PQL(
            columns=[pql.PQLColumn(name="value", query=bind(expression))],
            filters=[pql.PQLFilter(query=bind(statement)) for statement in filters],
        )
        frame = self._view.km._export(query, limit=limit, offset=offset, distinct=True)
        return tuple(DropdownOption(value, str(value)) for value in frame["value"].tolist() if not _is_null(value))

    def _manual_options(self) -> tuple[DropdownOption, ...]:
        options = []
        items = self.settings.get("items")
        for item in items if isinstance(items, list) else ():
            if not isinstance(item, Mapping):
                continue
            value = item.get("value")
            variables = _update(item, "onClick").get("variables")
            if isinstance(variables, Mapping):
                value = variables.get(self.variable_key, value)
            elif isinstance(variables, list):
                value = next((v.get("value", value) for v in variables
                              if isinstance(v, Mapping) and v.get("name") == self.variable_key), value)
            label = item.get("displayName") or item.get("label") or item.get("id")
            options.append(DropdownOption(value, str(label or value or "")))
        return tuple(options)

    def _attribute_query(self) -> tuple[str, list[str]] | None:
        for source in self._component.settings.data_sources:
            if source.id == self.data_source_id:
                for attribute in source.attributes:
                    if attribute.id == self.attribute_id:
                        return attribute.pql, [item.to_pql().query for item in source.filters]
        return None

    def _check_key_count(self, count: int) -> None:
        if count < 1:
            raise self._binding_error("must bind at least one input variable")

    def _decode(self, value: str | None) -> object:
        if self.selection_mode != "multiple":
            return value
        if value is None:
            return ()
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return (value,)
        return tuple(decoded) if isinstance(decoded, list) else (decoded,)


class SelectorHandle(DropdownHandle):
    """A selector; it behaves like a dropdown."""


class DatePickerHandle(ViewInputHandle):
    """A date picker; its value is a ``date``, or a :class:`DateRange` for a range."""

    @property
    def range_selection(self) -> bool:
        return self.settings.get("rangeSelection") is True

    @property
    def variable_key(self) -> str:
        if self.range_selection:
            raise ComponentVariableError(
                f"Date picker {self.id!r} is a range; use start_variable_key and end_variable_key."
            )
        return super().variable_key

    @property
    def start_variable_key(self) -> str | None:
        return self._range_key("startDate")

    @property
    def end_variable_key(self) -> str | None:
        return self._range_key("endDate")

    @property
    def minimum_date(self) -> str | None:
        value = self.settings.get("minDate")
        return value if isinstance(value, str) else None

    @property
    def maximum_date(self) -> str | None:
        value = self.settings.get("maxDate")
        return value if isinstance(value, str) else None

    @property
    def value(self) -> date | DateRange | None:
        details = self.details()
        if isinstance(details, DateRangeDetails):
            return DateRange(self._decode(details.start.value), self._decode(details.end.value))
        return self._decode(details.value)

    def details(self) -> InputVariableValue | DateRangeDetails:
        """The current record of the date, or of both ends of a range, in one read."""
        if not self.range_selection:
            return super().details()
        self._check_binding()
        values = self._view._input_values()
        return DateRangeDetails(
            self._read(values, self.start_variable_key), self._read(values, self.end_variable_key)
        )

    def _range_key(self, role: str) -> str | None:
        variables = _update(self.settings).get("variables")
        key = variables.get(role) if isinstance(variables, Mapping) else None
        return key if isinstance(key, str) else None

    def _check_key_count(self, count: int) -> None:
        expected = 2 if self.range_selection else 1
        if count != expected:
            raise self._binding_error(f"must bind exactly {expected} input variable{'s' if expected > 1 else ''}")

    def _decode(self, value: str | None) -> date | None:
        """An ISO date, or a Celonis epoch timestamp in seconds or milliseconds."""
        if value is None:
            return None
        candidate = value.strip().strip("\"'")
        try:
            if candidate[4:5] == "-" and candidate[7:8] == "-":
                return date.fromisoformat(candidate[:10])
            epoch = int(candidate)
            seconds = epoch / 1000 if abs(epoch) >= 100_000_000_000 else epoch
            return datetime.fromtimestamp(seconds, tz=timezone.utc).date()
        except (OverflowError, OSError, ValueError) as exc:
            raise ResourceResolutionError(f"Date picker {self.id!r} returned invalid date {value!r}.") from exc


class CheckboxHandle(ViewInputHandle):
    """A checkbox; its value is a ``bool``."""

    def _decode(self, value: str | None) -> bool | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in ("true", "false"):
            raise ResourceResolutionError(f"Checkbox {self.id!r} returned invalid boolean {value!r}.")
        return normalized == "true"


INPUT_HANDLES: dict[str, type[ViewInputHandle]] = {
    "input-box": InputBoxHandle,
    "input-dropdown": DropdownHandle,
    "input-selector": SelectorHandle,
    "selector": SelectorHandle,
    "input-date-picker": DatePickerHandle,
    "date-picker": DatePickerHandle,
    "input-checkbox": CheckboxHandle,
    "checkbox": CheckboxHandle,
}
"""Handle class for each supported input component type."""


def _is_null(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):  # Arrays are values, not nulls.
        return False
