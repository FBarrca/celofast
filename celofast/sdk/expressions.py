"""PQL expression handling: rewriting bridged key counts at pull, and binding
KM input variables (``${name}``) at query time.

Both work on the same tokens, so comments, quoted identifiers, and string
literals are never mistaken for code.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping

from celofast.exceptions import UnresolvedVariableError
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


def placeholders(expression: str) -> set[str]:
    """Names of ``${name}`` placeholders in code and string literals, not comments."""
    return {
        name
        for token in _TOKENS.finditer(expression) if token.lastgroup in ("variable", "string")
        for name in _VARIABLE.findall(token.group())
    }


def input_literal(value: str, data_type: str | None, *, quoted: bool = False) -> str:
    """The PQL text for one input value, as the KM substitutes it.

    Inside a string literal the value is only escaped. Otherwise text inputs
    become string literals, unless numeric: numeric text inputs are also used
    as numbers. Booleans become 1/0; numbers and PQL inputs are inserted as is.
    """
    if quoted:
        return _escape(value)
    if data_type == "TEXT" and not _NUMBER.fullmatch(value):
        return "'" + _escape(value) + "'"
    if data_type == "BOOLEAN" and value.casefold() in ("true", "false"):
        return "1" if value.casefold() == "true" else "0"
    return value


def bind_inputs(
    expression: str, value: Callable[[str], str | None], types: Mapping[str, str | None]
) -> str:
    """Replace every placeholder with ``value(name)``, formatted by its data type.

    Raises ``UnresolvedVariableError`` for a placeholder without a value.
    """
    def replace(match: re.Match[str], quoted: bool) -> str:
        name = match.group(1)
        text = value(name)
        if text is None:
            raise UnresolvedVariableError(
                f"KM input variable ${{{name}}} has no value or default; set one in the KM."
            )
        return input_literal(text, types.get(name), quoted=quoted)

    def bind(token: re.Match[str]) -> str:
        if token.lastgroup in ("variable", "string"):
            quoted = token.lastgroup == "string"
            return _VARIABLE.sub(lambda match: replace(match, quoted), token.group())
        return token.group()

    return _TOKENS.sub(bind, expression)


class Expressions:
    """Rewrite ``PU_COUNT`` of a key through a unique shared child table.

    A bridged count becomes ``PU_COUNT_DISTINCT(target, BIND(bridge, key))``
    so each related source object counts once. A referenced calculated
    attribute or KPI that contains such a count is inlined with the rewrite;
    every other reference, including input-dependent ones, stays as it is and
    Celonis resolves it with the KM's current values.
    """

    def __init__(self, capture: Capture) -> None:
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
            return f"({expanded}\n)" if expanded != self.definitions[key] else token.group()

        return _TOKENS.sub(replace, expression)

    def resolve(self, expression: str) -> str:
        """The expression with bridged key counts rewritten; everything else is kept."""
        return self._expand(expression)


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
