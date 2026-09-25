"""KM input variables (``${name}``): inlining the references that use them at
pull, and binding them at query time.

Data exports do not bind placeholders written in the query, and bind the ones
inside a referenced calculated attribute or KPI raw (a TEXT value becomes an
unquoted name; verified live). So pull inlines every input-dependent reference
with its placeholders kept, and each read binds them all with typed literals.
Every other reference stays as it is; Celonis resolves it from the KM.

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
    rf"|(?P<kpi>(?i:\bKPI)\s*\(\s*(?:{_IDENTIFIER}|[A-Za-z_][\w$]*)\s*\))"
    rf"|(?P<column>{_IDENTIFIER}\s*\.\s*{_IDENTIFIER})"
    rf"|(?P<identifier>{_IDENTIFIER})"
    r"|(?P<variable>\$\{\w+\})"
)
_VARIABLE = re.compile(r"\$\{(\w+)\}")
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


def _names(expression: str) -> tuple[str, ...]:
    """The case-folded identifiers of a column reference or quoted KPI name."""
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



class References:
    """Inline references to input-dependent calculated attributes and KPIs.

    An attribute or KPI depends on an input when its definition, or one it
    references, contains a placeholder. Such a reference is replaced by its
    expanded definition; every other reference is kept. Raises ``ValueError``
    for a reference cycle.
    """

    def __init__(self, capture: Capture) -> None:
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
            # KM expressions reference a record by its table or by its ID.
            owners = {table.casefold(), str(record.get("id", table)).casefold()}
            for collection in ("attributes", "newAttributes", "augmentedAttributes"):
                for attribute in record.get(collection) or ():
                    id_ = attribute.get("id") if isinstance(attribute, dict) else None
                    expression = attribute.get("pql") if isinstance(attribute, dict) else None
                    if not isinstance(id_, str) or not isinstance(expression, str):
                        continue
                    for owner in owners:
                        key = (owner, id_.casefold())
                        # A catalog column must never expand into its own definition.
                        token = _TOKENS.fullmatch(expression.strip())
                        if key not in physical and not (token and token.lastgroup == "column"
                                                        and _names(expression) == key):
                            self.definitions.setdefault(key, expression)

    def _expand(self, expression: str, stack: tuple[tuple[str, ...], ...] = ()) -> str:
        def replace(token: re.Match[str]) -> str:
            if token.lastgroup == "kpi":
                name = token.group().split("(", 1)[1][:-1].strip()
                key = _names(name) if name.startswith('"') else (name.casefold(),)
            elif token.lastgroup == "column":
                key = _names(token.group())
            else:
                return token.group()
            if key not in self.definitions:
                return token.group()
            if key in stack:
                raise ValueError("cyclic calculated attribute or KPI: " + ".".join(key))
            if key not in self.cache:
                self.cache[key] = self._expand(self.definitions[key], (*stack, key))
            expanded = self.cache[key]
            # A newline keeps a trailing line comment from consuming what follows.
            return f"({expanded}\n)" if placeholders(expanded) else token.group()

        return _TOKENS.sub(replace, expression)

    def resolve(self, expression: str) -> str:
        """The expression with every input-dependent reference inlined."""
        return self._expand(expression)
