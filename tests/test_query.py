from copy import deepcopy

import pytest
from saolapy.pql.base import OrderByColumn, PQL, PQLColumn

from celofast import QueryValidationError, UnresolvedVariableError
from celofast.query import bind_variables, query_from_pql, query_to_pql


def test_query_definition_round_trips_native_pql_without_mutation():
    definition = {
        "columns": {
            "Supplier": '"Vendor"."Name"',
            "Value": 'KPI("value")',
        },
        "filters": ["FILTER @active_suppliers;"],
        "order_by": [{"pql": 'KPI("value")', "ascending": False}],
    }
    original = deepcopy(definition)

    native = query_to_pql(definition)

    assert [(item.name, item.query) for item in native.columns] == list(
        definition["columns"].items()
    )
    assert [item.query for item in native.filters] == definition["filters"]
    assert [(item.query, item.ascending) for item in native.order_by_columns] == [
        ('KPI("value")', False)
    ]
    assert query_from_pql(native) == definition
    assert definition == original


def test_query_defaults_optional_lists_and_rejects_unknown_fields():
    native = query_to_pql({"columns": {"id": '"Cases"."ID"'}})

    assert native.filters == []
    assert native.order_by_columns == []

    with pytest.raises(QueryValidationError, match="Unknown query field"):
        query_to_pql({"columns": {"id": '"Cases"."ID"'}, "limit": 10})


@pytest.mark.parametrize(
    "definition, message",
    [
        ({"columns": {}}, "non-empty mapping"),
        ({"columns": {"": '"Cases"."ID"'}}, "non-empty string alias"),
        ({"columns": {"id": ""}}, "non-empty PQL"),
        ({"columns": {"id": "x"}, "filters": [""]}, "non-empty PQL"),
        (
            {"columns": {"id": "x"}, "order_by": [{"pql": "x", "ascending": "yes"}]},
            "must be a boolean",
        ),
    ],
)
def test_query_validation(definition, message):
    with pytest.raises(QueryValidationError, match=message):
        query_to_pql(definition)


def test_native_duplicate_column_names_are_rejected():
    native = PQL(
        columns=[
            PQLColumn(name="id", query='"Cases"."ID"'),
            PQLColumn(name="id", query='"Cases"."OTHER_ID"'),
        ],
        order_by_columns=[OrderByColumn(query='"Cases"."ID"')],
    )

    with pytest.raises(QueryValidationError, match="duplicate column"):
        query_from_pql(native)


def test_bindings_replace_code_but_not_comments():
    expression = "${days} -- ${ignored}\n/* ${also_ignored} */ + ${offset}"

    assert bind_variables(expression, {"days": "30", "offset": "1"}) == (
        "30 -- ${ignored}\n/* ${also_ignored} */ + 1"
    )


def test_unresolved_binding_fails_before_execution():
    with pytest.raises(UnresolvedVariableError, match=r"\$\{days\}"):
        query_to_pql({"columns": {"value": "${days}"}})
