"""Resolve input-dependent attributes and KPIs in a local capture only."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from celofast.sdk.capture import Capture, record_table


_IDENTIFIER = r'"(?:\\.|""|[^"\\])*"'
_TOKENS = re.compile(
    r"(?P<comment>/\*[\s\S]*?\*/|--[^\r\n]*)"
    r"|(?P<string>'(?:\\.|''|[^'\\])*')"
    rf"|(?P<count>(?i:\bPU_COUNT)\s*\(\s*{_IDENTIFIER}\s*,\s*{_IDENTIFIER}\s*\.\s*{_IDENTIFIER}\s*\))"
    rf"|(?P<kpi>(?i:\bKPI)\s*\(\s*(?:{_IDENTIFIER}|[A-Za-z_][\w$]*)\s*\))"
    rf"|(?P<column>{_IDENTIFIER}\s*\.\s*{_IDENTIFIER})"
    rf"|(?P<identifier>{_IDENTIFIER})"
    r"|(?P<variable>\$\{\w+\})"
)
_VARIABLE = re.compile(r"\$\{(\w+)\}")
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


def _column_key(expression: str) -> tuple[str, ...]:
    return tuple(name[1:-1].replace('""', '"').casefold()
                 for name in re.findall(_IDENTIFIER, expression))


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


class Expressions:
    """Inline only dependencies that use inputs; leave physical columns intact.

    Defaults are frozen at pull, so validation and generated reads use identical
    PQL instead of delegating nested substitution to the live KM. The capture
    stays lossless and no request writes to Celonis.
    """

    def __init__(self, capture: Capture) -> None:
        self.inputs = capture.input_variables or {}
        self.count_bridges = _count_bridges(capture)
        physical = {
            (table.casefold(), name.casefold())
            for table, metadata in (capture.tables or {}).items()
            for name in metadata["columns"]
        }
        self.definitions: dict[tuple[str, ...], str] = {}
        self.cache: dict[tuple[str, ...], str] = {}
        layer = capture.definition
        # Parameterized KPIs retain their server-side argument semantics.
        for kpi in layer.get("kpis") or ():
            if isinstance(kpi, dict) and not kpi.get("parameters"):
                id_, expression = kpi.get("id"), kpi.get("pql")
                if isinstance(id_, str) and isinstance(expression, str):
                    self.definitions[(id_.casefold(),)] = expression
        for record in layer.get("records") or ():
            table = record_table(record.get("pql")) if isinstance(record, dict) else None
            if table is None:
                continue
            for collection in ("attributes", "newAttributes", "augmentedAttributes"):
                for attribute in record.get(collection) or ():
                    id_ = attribute.get("id") if isinstance(attribute, dict) else None
                    expression = attribute.get("pql") if isinstance(attribute, dict) else None
                    if not isinstance(id_, str) or not isinstance(expression, str):
                        continue
                    key = (table.casefold(), id_.casefold())
                    # A catalog column must never expand into its own definition.
                    token = _TOKENS.fullmatch(expression.strip())
                    if key not in physical and not (token and token.lastgroup == "column"
                                                    and _column_key(expression) == key):
                        self.definitions.setdefault(key, expression)

    def _uses_inputs(self, expression: str) -> bool:
        return any(
            name in self.inputs
            for token in _TOKENS.finditer(expression) if token.lastgroup != "comment"
            for name in _VARIABLE.findall(token.group())
        )

    def _expand(self, expression: str, stack: tuple[tuple[str, ...], ...] = ()) -> str:
        def replace(token: re.Match[str]) -> str:
            if token.lastgroup == "count":
                text = token.group()
                bridge = self.count_bridges.get(_column_key(text))
                if bridge is not None:
                    target, source, column = re.findall(_IDENTIFIER, text)
                    quoted_bridge = '"' + bridge.replace('"', '""') + '"'
                    return f"PU_COUNT_DISTINCT({target}, BIND({quoted_bridge}, {source}.{column}))"
                start = text.index("(") + 1
                return text[:start] + self._expand(text[start:-1], stack) + ")"
            if token.lastgroup not in ("column", "kpi"):
                return token.group()
            if token.lastgroup == "kpi":
                name = token.group().split("(", 1)[1][:-1].strip()
                key = _column_key(name) if name.startswith('"') else (name.casefold(),)
            else:
                key = _column_key(token.group())
            if key not in self.definitions:
                return token.group()
            if key in stack:
                raise ValueError("cyclic calculated attribute or KPI: " + ".".join(key))
            if key not in self.cache:
                self.cache[key] = self._expand(self.definitions[key], (*stack, key))
            expanded = self.cache[key]
            changed = expanded != self.definitions[key] or self._uses_inputs(expanded)
            return f"({expanded}\n)" if changed else token.group()

        return _TOKENS.sub(replace, expression)

    def resolve(self, expression: str, *, bind_defaults: bool = True) -> str:
        expanded = self._expand(expression)
        if not bind_defaults:
            return expanded

        def value(match: re.Match[str], *, quoted: bool = False) -> str:
            definition: Mapping[str, Any] = self.inputs.get(match.group(1), {})
            default = definition.get("defaultValue")
            type_ = definition.get("dataType")
            if default is None or type_ not in ("TEXT", "NUMBER", "BOOLEAN", "PQL"):
                return match.group()
            text = str(default)
            if quoted:
                return _escape(text)
            # Numeric text inputs are also used as numeric PQL replacements.
            if type_ == "PQL" or _NUMBER.fullmatch(text):
                return text
            if type_ == "TEXT":
                return "'" + _escape(text) + "'"
            if type_ == "BOOLEAN" and text.casefold() in ("true", "false"):
                return "1" if text.casefold() == "true" else "0"
            return match.group()

        def bind(token: re.Match[str]) -> str:
            if token.lastgroup == "variable":
                return _VARIABLE.sub(value, token.group())
            if token.lastgroup == "string":
                return _VARIABLE.sub(lambda match: value(match, quoted=True), token.group())
            return token.group()

        return _TOKENS.sub(bind, expanded)


def _count_bridges(capture: Capture) -> dict[tuple[str, ...], str]:
    """Unique shared-child paths for counting source objects by their primary key."""
    tables = {name.casefold(): table for name, table in (capture.tables or {}).items()}
    joins = capture.joins or ()
    children: dict[str, set[str]] = {}
    candidates: dict[tuple[str, str], list[str]] = {}
    for left in joins:
        one, many = left["one"].casefold(), left["many"].casefold()
        children.setdefault(one, set()).add(many)
        for right in joins:
            source = right["one"].casefold()
            if right["many"].casefold() == many and source != one:
                candidates.setdefault((one, source), []).append(left["many"])
    def reaches(start: str, end: str) -> bool:
        pending, descendants = [start], set()
        while pending:
            table = pending.pop()
            if table not in descendants:
                descendants.add(table)
                pending.extend(children.get(table, ()))
        return end in descendants

    bridges: dict[tuple[str, ...], str] = {}
    for (target, source), paths in candidates.items():
        # Only bridge peer tables; preserve existing ancestor/descendant paths.
        key: list[str] = tables.get(source, {}).get("primary_key") or []
        if len(paths) == 1 and len(key) == 1 and not reaches(target, source) and not reaches(source, target):
            bridges[(target, source, key[0].casefold())] = paths[0]
    return bridges
