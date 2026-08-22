"""Serializable query definitions backed by native SaolaPy PQL objects."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import NotRequired, TypedDict, cast

from saolapy.pql.base import OrderByColumn, PQL, PQLColumn, PQLFilter

from celofast.exceptions import QueryValidationError, UnresolvedVariableError


class OrderByDefinition(TypedDict):
    """Describe one ordered expression in a :class:`QueryDefinition`.

    Attributes:
        pql: Native PQL expression, such as a column reference or ``KPI(...)``.
        ascending: Whether values are sorted low-to-high.  Defaults to
            ``True`` when omitted; set it to ``False`` for descending order.

    The expression is passed to SaolaPy unchanged.  CeloFast does not expand
    KPI names or Knowledge Model references on the client.
    """

    pql: str
    ascending: NotRequired[bool]


class QueryDefinition(TypedDict):
    """Compact, serializable representation of a native SaolaPy query.

    Attributes:
        columns: Non-empty mapping from output aliases to native PQL
            expressions.  Insertion order becomes the result-column order.
        filters: Optional list of complete native PQL filter statements.  A
            Knowledge Model filter reference should remain symbolic, for
            example ``"FILTER @active_suppliers;"``.
        order_by: Optional ordered list of :class:`OrderByDefinition` values.
            Insertion order is preserved in the generated PQL.

    Query definitions are plain dictionaries, so they can be serialized as
    JSON/YAML and reused across calls.  Validation rejects unknown top-level
    fields, empty expressions, and malformed ordering entries.

    Example:
        >>> query: QueryDefinition = {
        ...     "columns": {"Supplier": '"Vendor"."Name"'},
        ...     "filters": ['FILTER "Vendor"."Country" = \'DE\';'],
        ...     "order_by": [{"pql": '"Vendor"."Name"'}],
        ... }
    """

    columns: dict[str, str]
    filters: NotRequired[list[str]]
    order_by: NotRequired[list[OrderByDefinition]]


_QUERY_KEYS = frozenset(("columns", "filters", "order_by"))
_ORDER_BY_KEYS = frozenset(("pql", "ascending"))
_COMMENT_SPLIT_RE = re.compile(r"(--.*?$|/\*[\s\S]*?\*/)", re.MULTILINE)
_VARIABLE_RE = re.compile(r"\$\{(\w+)\}")


def validate_variables(
    variables: Mapping[str, str] | None,
) -> dict[str, str]:
    """Validate and copy exact string bindings for query templates.

    Args:
        variables: Mapping used to replace ``${name}`` placeholders, or
            ``None`` for no bindings.  Both keys and values must be strings;
            values are not converted to PQL literals or otherwise escaped.

    Returns:
        A new regular dictionary, so subsequent caller mutations cannot alter
        the validated input used by CeloFast.

    Raises:
        QueryValidationError: If ``variables`` is not a mapping of non-empty
            string names to string values.
    """

    if variables is None:
        return {}
    if not isinstance(variables, Mapping):
        raise QueryValidationError("variables must be a mapping of strings.")

    bindings: dict[str, str] = {}
    for key, value in variables.items():
        if not isinstance(key, str) or not key:
            raise QueryValidationError("Variable names must be non-empty strings.")
        if not isinstance(value, str):
            raise QueryValidationError(
                f"Variable {key!r} must be an exact string replacement."
            )
        bindings[key] = value
    return bindings


def validate_query(query: Mapping[str, object]) -> QueryDefinition:
    """Validate and copy a mapping into the public query contract.

    Args:
        query: Mapping with required ``columns`` and optional ``filters`` and
            ``order_by`` fields.  Expressions are treated as native PQL and
            are not semantically rewritten.

    Returns:
        A fresh :class:`QueryDefinition` containing copied lists and mappings.
        Column and ordering insertion order is preserved.

    Raises:
        QueryValidationError: If a top-level field is unknown, columns are
            empty, or any filter/order entry is malformed.  The input object
            is never mutated.
    """

    if not isinstance(query, Mapping):
        raise QueryValidationError("query must be a mapping.")

    unknown_keys = set(query) - _QUERY_KEYS
    if unknown_keys:
        rendered = ", ".join(sorted(repr(key) for key in unknown_keys))
        raise QueryValidationError(f"Unknown query field(s): {rendered}.")

    raw_columns = query.get("columns")
    if not isinstance(raw_columns, Mapping) or not raw_columns:
        raise QueryValidationError("query.columns must be a non-empty mapping.")

    columns: dict[str, str] = {}
    for alias, expression in raw_columns.items():
        if not isinstance(alias, str) or not alias.strip():
            raise QueryValidationError("Every query column needs a non-empty string alias.")
        if not isinstance(expression, str) or not expression.strip():
            raise QueryValidationError(
                f"Column {alias!r} needs a non-empty PQL expression."
            )
        columns[alias] = expression

    raw_filters = query.get("filters", [])
    if not isinstance(raw_filters, list):
        raise QueryValidationError("query.filters must be a list of PQL strings.")

    filters: list[str] = []
    for index, expression in enumerate(raw_filters):
        if not isinstance(expression, str) or not expression.strip():
            raise QueryValidationError(
                f"Filter at index {index} must be a non-empty PQL string."
            )
        filters.append(expression)

    raw_order_by = query.get("order_by", [])
    if not isinstance(raw_order_by, list):
        raise QueryValidationError("query.order_by must be a list of mappings.")

    order_by: list[OrderByDefinition] = []
    for index, item in enumerate(raw_order_by):
        if not isinstance(item, Mapping):
            raise QueryValidationError(
                f"Ordering at index {index} must be a mapping."
            )
        unknown_order_keys = set(item) - _ORDER_BY_KEYS
        if unknown_order_keys:
            rendered = ", ".join(sorted(repr(key) for key in unknown_order_keys))
            raise QueryValidationError(
                f"Unknown order_by field(s) at index {index}: {rendered}."
            )
        expression = item.get("pql")
        if not isinstance(expression, str) or not expression.strip():
            raise QueryValidationError(
                f"Ordering at index {index} needs a non-empty PQL expression."
            )
        ascending = item.get("ascending", True)
        if not isinstance(ascending, bool):
            raise QueryValidationError(
                f"order_by[{index}].ascending must be a boolean."
            )
        order_by.append(OrderByDefinition(pql=expression, ascending=ascending))

    return QueryDefinition(columns=columns, filters=filters, order_by=order_by)


def bind_variables(pql: str, variables: Mapping[str, str] | None = None) -> str:
    """Replace ``${name}`` placeholders in PQL code without editing comments.

    Args:
        pql: PQL text containing zero or more ``${name}`` placeholders.
        variables: Exact string replacements.  A placeholder in a SQL/PQL
            line or block comment is intentionally left untouched.

    Returns:
        PQL text with every code placeholder replaced.

    Raises:
        QueryValidationError: If ``variables`` has invalid keys or values.
        UnresolvedVariableError: If executable PQL still contains a
            placeholder for which no binding was supplied.

    Notes:
        Replacement is deliberately textual.  It does not provide a Python
        value-conversion layer and does not override server-managed Knowledge
        Model variables.
    """

    bindings = validate_variables(variables)

    def replace_code(code: str) -> str:
        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in bindings:
                raise UnresolvedVariableError(
                    f"Unresolved query variable ${{{name}}}."
                )
            return bindings[name]

        return _VARIABLE_RE.sub(replace, code)

    parts = _COMMENT_SPLIT_RE.split(pql)
    for index in range(0, len(parts), 2):
        parts[index] = replace_code(parts[index])
    return "".join(parts)


def query_to_pql(
    query: Mapping[str, object],
    *,
    variables: Mapping[str, str] | None = None,
) -> PQL:
    """Compile a dictionary query into a native SaolaPy :class:`PQL`.

    Args:
        query: Reusable query definition containing columns and optional
            filters/orderings.
        variables: Optional exact string bindings for ``${name}`` placeholders
            in columns, filters, and ordering expressions.

    Returns:
        A new SaolaPy ``PQL`` with ``PQLColumn``, ``PQLFilter``, and
        ``OrderByColumn`` objects in the same order as the input mapping/list.
        The query is not executed.

    Raises:
        QueryValidationError: If the definition is malformed.
        UnresolvedVariableError: If a non-comment placeholder has no binding.
    """

    definition = validate_query(query)
    return PQL(
        columns=[
            PQLColumn(name=alias, query=bind_variables(expression, variables))
            for alias, expression in definition["columns"].items()
        ],
        filters=[
            PQLFilter(query=bind_variables(expression, variables))
            for expression in definition["filters"]
        ],
        order_by_columns=[
            OrderByColumn(
                query=bind_variables(item["pql"], variables),
                ascending=item["ascending"],
            )
            for item in definition["order_by"]
        ],
    )


def query_from_pql(query: PQL) -> QueryDefinition:
    """Convert native SaolaPy ``PQL`` into a :class:`QueryDefinition`.

    Args:
        query: Native PQL returned by SaolaPy or by a PyCelonis component such
            as ``Table.get_query()``.

    Returns:
        A serializable dictionary containing every native column, filter, and
        ordering expression.  This includes configured data-source columns
        that may be hidden in the View UI and preserves symbolic expressions
        such as ``FILTER @filter_id;``.

    Raises:
        QueryValidationError: If native PQL contains duplicate column aliases
            or otherwise violates the public query contract.
    """

    columns: dict[str, str] = {}
    for column in query.columns:
        if column.name in columns:
            raise QueryValidationError(
                f"Native PQL contains duplicate column name {column.name!r}."
            )
        columns[column.name] = column.query

    definition = QueryDefinition(
        columns=columns,
        filters=[filter_.query for filter_ in query.filters],
        order_by=[
            OrderByDefinition(pql=item.query, ascending=item.ascending)
            for item in query.order_by_columns
        ],
    )
    return cast(QueryDefinition, validate_query(cast(Mapping[str, object], definition)))
