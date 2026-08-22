from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from pycelonis.celonis import Celonis

from celofast.services.knowledge_model_service import KnowledgeModelService


def test_query_resolves_km_and_uses_saolapy_data_model():
    data_model = SimpleNamespace(id="data-model-id")
    knowledge_model = SimpleNamespace(
        name="Example KM",
        root_with_key="package-key.km-key",
        get_content=lambda: SimpleNamespace(data_model_id="data-model-id"),
    )
    celonis = SimpleNamespace(
        studio=SimpleNamespace(),
        data_integration=SimpleNamespace(),
    )
    expected = object()
    saola_frame = MagicMock()
    saola_frame.head.return_value = expected

    with patch(
        "celofast.services.knowledge_model_service.PyCelonisDataFrame.from_pql",
        return_value=saola_frame,
    ) as from_pql:
        service = object.__new__(KnowledgeModelService)
        service.knowledge_model_reference = "space-id.package-id.Example KM"
        service.celonis = cast(Celonis, celonis)
        service.knowledge_model = knowledge_model
        service.data_model = data_model
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


def test_direct_construction_is_rejected():
    with pytest.raises(TypeError, match="from_studio"):
        KnowledgeModelService("space-id.package-id.Example KM")


def test_from_studio_resolves_context_without_repeating_lookups():
    client = cast(Celonis, object())
    knowledge_model = SimpleNamespace(name="Orders KM")
    data_model = object()
    context = SimpleNamespace(
        knowledge_model=knowledge_model,
        data_model=data_model,
    )

    with (
        patch(
            "celofast.services.knowledge_model_service.get_celonis",
            return_value=client,
        ) as get_client,
        patch(
            "celofast.services.knowledge_model_service.resolve_studio_context",
            return_value=context,
        ) as resolve_context,
    ):
        service = KnowledgeModelService.from_studio(
            space_id="space-id",
            package_id="package-id",
            view_key="orders-view",
        )

    assert service.celonis is client
    assert service.knowledge_model is knowledge_model
    assert service.data_model is data_model
    assert service.knowledge_model_reference == "space-id.package-id.Orders KM"
    get_client.assert_called_once_with()
    resolve_context.assert_called_once_with(
        client,
        space_id="space-id",
        package_id="package-id",
        view_key="orders-view",
        knowledge_model_key=None,
        data_model_id=None,
        data_pool_id=None,
    )


def test_from_studio_can_resolve_knowledge_model_directly():
    client = cast(Celonis, object())
    knowledge_model = SimpleNamespace(name="Orders KM")
    data_model = object()
    context = SimpleNamespace(
        knowledge_model=knowledge_model,
        data_model=data_model,
    )

    with patch(
        "celofast.services.knowledge_model_service.resolve_knowledge_model_context",
        return_value=context,
    ) as resolve_context:
        service = KnowledgeModelService.from_studio(
            client,
            space_id="space-id",
            package_id="package-id",
            km_key="orders-km",
        )

    assert service.celonis is client
    assert service.knowledge_model is knowledge_model
    assert service.data_model is data_model
    resolve_context.assert_called_once_with(
        client,
        space_id="space-id",
        package_id="package-id",
        knowledge_model_key="orders-km",
        data_model_id=None,
        data_pool_id=None,
    )


def test_from_studio_requires_exactly_one_context_key():
    with pytest.raises(ValueError, match="exactly one"):
        KnowledgeModelService.from_studio(
            cast(Celonis, object()),
            space_id="space-id",
            package_id="package-id",
        )

    with pytest.raises(ValueError, match="exactly one"):
        KnowledgeModelService.from_studio(
            cast(Celonis, object()),
            space_id="space-id",
            package_id="package-id",
            view_key="orders-view",
            km_key="orders-km",
        )
