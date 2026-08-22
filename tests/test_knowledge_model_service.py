from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from celofast.services.knowledge_model_service import KnowledgeModelService


def test_query_resolves_km_and_uses_saolapy_data_model():
    data_model = SimpleNamespace(id="data-model-id")
    knowledge_model = SimpleNamespace(
        name="Example KM",
        root_with_key="package-key.km-key",
        get_content=lambda: SimpleNamespace(data_model_id="data-model-id"),
    )
    package = SimpleNamespace(get_knowledge_models=lambda: [knowledge_model])
    space = SimpleNamespace(get_package=lambda package_id: package)
    celonis = SimpleNamespace(
        studio=SimpleNamespace(get_space=lambda space_id: space),
        data_integration=SimpleNamespace(
            get_data_pools=lambda: [SimpleNamespace(get_data_models=lambda: [data_model])]
        ),
    )
    expected = object()
    saola_frame = MagicMock()
    saola_frame.head.return_value = expected

    with patch(
        "celofast.services.knowledge_model_service.PyCelonisDataFrame.from_pql",
        return_value=saola_frame,
    ) as from_pql:
        service = KnowledgeModelService("space-id.package-id.Example KM", celonis=celonis)
        result = service.query({"city": '"Customer"."City"'}, limit=10)

    assert result is expected
    assert from_pql.call_args.kwargs["data_model"] is data_model
    assert from_pql.call_args.args[0].columns[0].name == "city"
    assert from_pql.call_args.args[0].columns[0].query == '"Customer"."City"'
    saola_frame.head.assert_called_once_with(10)


def test_query_rejects_empty_attributes():
    celonis = MagicMock()
    service = object.__new__(KnowledgeModelService)

    try:
        service.query({}, limit=10)
    except ValueError as exc:
        assert str(exc) == "attribute_columns must contain at least one column."
    else:
        raise AssertionError("Expected empty attributes to be rejected")
