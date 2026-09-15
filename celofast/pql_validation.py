"""Local PQL structure checks; Celonis remains the authority for its grammar."""

from __future__ import annotations

import re

from celofast.exceptions import QueryValidationError

_TOKEN = re.compile(
    r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
    r"|@?[A-Za-z_]\w*|>=|<=|<>|!=|==|\|\||[()\[\]{},.;:+*/%<>=!-]"
)
_OPERATORS = {"=", "<", ">", "<=", ">=", "<>", "!=", "+", "-", "*", "/", "%", "||"}
_NEEDS_OPERAND = _OPERATORS | {"AND", "OR", "NOT", "IN", "LIKE", "IS", "BETWEEN"}


def _tokens(text: str) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(text):
        if text[index].isspace():
            index += 1
        elif text.startswith("--", index):
            end = text.find("\n", index + 2)
            index = len(text) if end < 0 else end + 1
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise QueryValidationError("Malformed PQL: unclosed comment.")
            index = end + 2
        elif text[index] in "\"'":
            quote = text[index]
            index += 1
            while index < len(text):
                if text[index] == "\\":
                    index += 2
                elif text[index] == quote:
                    if index + 1 < len(text) and text[index + 1] == quote:
                        index += 2
                    else:
                        index += 1
                        break
                else:
                    index += 1
            else:
                raise QueryValidationError("Malformed PQL: unclosed quoted value.")
            result.append(":quoted")
        elif text.startswith("${", index):
            end = text.find("}", index + 2)
            if end < 0 or not re.fullmatch(r"\w+", text[index + 2:end]):
                raise QueryValidationError("Malformed PQL: invalid template variable.")
            result.append(":variable")
            index = end + 1
        else:
            match = _TOKEN.match(text, index)
            if match is None:
                raise QueryValidationError(f"Malformed PQL near {text[index:index + 12]!r}.")
            result.append(match.group().upper())
            index = match.end()
    return result


def validate_pql(text: str, *, filter_: bool = False) -> None:
    """Reject incomplete statements, delimiters, quotes, and operators locally.

    This is a structural check, not a replacement for the engine's KM-aware
    parser. Valid-looking expressions with unknown functions or names are
    resolved by Celonis during execution.
    """
    tokens = _tokens(text)
    if filter_:
        if len(tokens) < 3 or tokens[0] != "FILTER" or tokens[-1] != ";":
            raise QueryValidationError("Raw filters must be complete FILTER condition; statements.")
        tokens = tokens[1:-1]
    if not tokens:
        raise QueryValidationError("Malformed PQL: empty expression.")
    if ";" in tokens or "FILTER" in tokens or "==" in tokens:
        raise QueryValidationError("Malformed PQL: unexpected statement or operator.")
    stack: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    previous = ""
    for token in tokens:
        if token in ("(", "[", "{"):
            stack.append(token)
        elif token in pairs:
            if not stack or stack.pop() != pairs[token]:
                raise QueryValidationError("Malformed PQL: unbalanced delimiters.")
            if previous in _NEEDS_OPERAND or previous == ",":
                raise QueryValidationError("Malformed PQL: missing operand.")
        if token in _OPERATORS and token not in {"+", "-"}:
            if not previous or previous in _NEEDS_OPERAND or previous in {"(", ","}:
                raise QueryValidationError("Malformed PQL: missing operand.")
        previous = token
    if stack:
        raise QueryValidationError("Malformed PQL: unbalanced delimiters.")
    if tokens[-1] in _NEEDS_OPERAND | {",", ".", "WHEN", "THEN", "ELSE"}:
        raise QueryValidationError("Malformed PQL: missing operand.")
    if filter_ and len(tokens) == 1 and not tokens[0].startswith(("@", ":variable")):
        raise QueryValidationError("Malformed PQL: filter requires a condition.")
