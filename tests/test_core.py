from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
import yaml
from pycelonis.celonis import Celonis

from celofast import CeloFast, ResourceNotFoundError


def make_client():
    data_model = SimpleNamespace(id="dm-id", pool_id="pool-id")
    data_pool = SimpleNamespace(get_data_models=MagicMock(return_value=[data_model]))
    knowledge_model = SimpleNamespace(
        id="km-id",
        key="orders-km",
        get_content=MagicMock(return_value=SimpleNamespace(data_model_id="dm-id")),
    )
    view_payload = {
        "metadata": {
            "key": "orders-view",
            "name": "Orders View",
            "knowledgeModelKey": "orders-km",
        },
        "components": [],
        "tabs": [],
    }
    view = SimpleNamespace(
        id="view-id",
        key="orders-view",
        serialized_content=yaml.safe_dump(view_payload),
        input_variable_definitions=[],
    )
    package = SimpleNamespace(
        get_knowledge_models=MagicMock(return_value=[knowledge_model]),
        get_views=MagicMock(return_value=[view]),
    )
    space = SimpleNamespace(get_package=MagicMock(return_value=package))
    client = SimpleNamespace(
        studio=SimpleNamespace(get_space=MagicMock(return_value=space)),
        data_integration=SimpleNamespace(
            get_data_pools=MagicMock(return_value=[data_pool])
        ),
    )
    return client, space, package, knowledge_model, view, data_pool


def test_celofast_resolves_scope_once_and_caches_native_contexts():
    client, space, package, knowledge_model, _, data_pool = make_client()
    cf = CeloFast("space-id", "package-id", client=cast(Celonis, client))

    first_km = cf.km("orders-km")
    second_km = cf.km("orders-km")
    first_view = cf.view("orders-view")
    second_view = cf.view("orders-view")

    assert cf.client is client
    assert cf.space is space
    assert cf.package is package
    assert first_km is second_km
    assert first_view is second_view
    assert first_view.km is first_km
    client.studio.get_space.assert_called_once_with("space-id")
    space.get_package.assert_called_once_with("package-id")
    package.get_knowledge_models.assert_called_once_with()
    package.get_views.assert_called_once_with()
    knowledge_model.get_content.assert_called_once_with()
    client.data_integration.get_data_pools.assert_called_once_with()
    data_pool.get_data_models.assert_called_once_with()


def test_exporting_view_table_does_not_resolve_knowledge_model_or_data_model():
    client, _, package, knowledge_model, _, _ = make_client()
    cf = CeloFast("space-id", "package-id", client=cast(Celonis, client))

    assert cf.view("orders-view").tables == ()

    package.get_knowledge_models.assert_not_called()
    knowledge_model.get_content.assert_not_called()
    client.data_integration.get_data_pools.assert_not_called()


def test_view_handles_cache_per_variable_binding():
    client, *_ = make_client()
    cf = CeloFast("space-id", "package-id", client=cast(Celonis, client))

    first = cf.view("orders-view", variables={"days": "7"})
    same = cf.view("orders-view", variables={"days": "7"})
    different = cf.view("orders-view", variables={"days": "30"})

    assert first is same
    assert different is not first


def test_exact_missing_resource_key_has_contextual_error():
    client, *_ = make_client()
    cf = CeloFast("space-id", "package-id", client=cast(Celonis, client))

    with pytest.raises(ResourceNotFoundError, match="missing-km"):
        cf.km("missing-km")
