from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from pycelonis.ems.data_integration.data_model import DataModel
from pycelonis.ems.studio.content_node.knowledge_model import KnowledgeModel

from celofast import QueryValidationError
from celofast.resources.knowledge_model import KnowledgeModelHandle


def make_handle() -> KnowledgeModelHandle:
    return KnowledgeModelHandle(
        cast(KnowledgeModel, MagicMock()),
        cast(DataModel, MagicMock()),
    )


def test_execute_uses_native_connector_and_to_pandas_options():
    handle = make_handle()
    lazy_frame = MagicMock()
    expected = object()
    lazy_frame.to_pandas.return_value = expected

    with patch(
        "celofast.resources.knowledge_model.DataFrame.from_pql",
        return_value=lazy_frame,
    ) as from_pql:
        result = handle.execute(
            {
                "columns": {"value": 'KPI("value") + ${offset}'},
                "filters": ["FILTER @active;"],
            },
            variables={"offset": "1"},
            limit=100,
            offset=10,
            distinct=True,
        )

    assert result is expected
    pql = from_pql.call_args.args[0]
    assert pql.columns[0].query == 'KPI("value") + 1'
    assert pql.filters[0].query == "FILTER @active;"
    assert from_pql.call_args.kwargs["saola_connector"] is handle._connector
    lazy_frame.to_pandas.assert_called_once_with(
        limit=100,
        offset=10,
        distinct=True,
    )


def test_no_implicit_limit_and_native_export_errors_are_preserved():
    handle = make_handle()
    lazy_frame = MagicMock()
    lazy_frame.to_pandas.side_effect = RuntimeError("native failure")

    with patch(
        "celofast.resources.knowledge_model.DataFrame.from_pql",
        return_value=lazy_frame,
    ):
        with pytest.raises(RuntimeError, match="native failure"):
            handle.execute({"columns": {"id": '"Cases"."ID"'}})

    lazy_frame.to_pandas.assert_called_once_with(
        limit=None,
        offset=None,
        distinct=False,
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": -1},
        {"offset": -1},
        {"limit": True},
        {"distinct": "yes"},
    ],
)
def test_invalid_execution_options_are_rejected(kwargs):
    with pytest.raises(QueryValidationError):
        make_handle().execute({"columns": {"id": '"Cases"."ID"'}}, **kwargs)
