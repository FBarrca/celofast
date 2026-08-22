from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
import yaml
from pycelonis.celonis import Celonis
from pycelonis.ems.apps.content_node.view.content import ViewContent
from pycelonis_core.client.client import Client
from pycelonis_core.utils.errors import PyCelonisNotFoundError

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
    assert cf.mode == "draft"
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


def test_kms_sharing_a_data_model_share_augmentation_collection():
    client, _, package, knowledge_model, _, _ = make_client()
    second_knowledge_model = SimpleNamespace(
        id="second-km-id",
        key="second-km",
        get_content=MagicMock(return_value=SimpleNamespace(data_model_id="dm-id")),
    )
    package.get_knowledge_models.return_value = [
        knowledge_model,
        second_knowledge_model,
    ]
    cf = CeloFast("space-id", "package-id", client=cast(Celonis, client))

    first = cf.km("orders-km")
    second = cf.km("second-km")

    assert first.data_model is second.data_model
    assert first.augmentation_tables is second.augmentation_tables


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


def make_published_client(*, missing_km: bool = False):
    data_model = SimpleNamespace(id="dm-id", pool_id="pool-id")
    data_pool = SimpleNamespace(get_data_models=MagicMock(return_value=[data_model]))
    listed_view = SimpleNamespace(id="published-view-id", key="orders-view")
    hydrated_view = SimpleNamespace(
        id="published-view-id",
        key="orders-view",
        input_variable_definitions=[],
        get_content=MagicMock(),
    )
    package_client = MagicMock(spec=Client)
    package = SimpleNamespace(
        root_node_key="published-package-root",
        space_id="space-id",
        client=package_client,
        get_views=MagicMock(return_value=[listed_view]),
        get_view=MagicMock(return_value=hydrated_view),
    )
    space = SimpleNamespace(get_package=MagicMock(return_value=package))
    client = SimpleNamespace(
        apps=SimpleNamespace(get_space=MagicMock(return_value=space)),
        data_integration=SimpleNamespace(
            get_data_pools=MagicMock(return_value=[data_pool])
        ),
    )
    final_content = SimpleNamespace(data_model_id="dm-id")
    get_content = MagicMock(
        side_effect=(
            PyCelonisNotFoundError("missing published KM")
            if missing_km
            else None
        ),
        return_value=final_content,
    )
    return client, space, package, hydrated_view, get_content


def test_published_mode_uses_apps_and_hydrates_views():
    client, space, package, hydrated_view, _ = make_published_client()
    view_content = ViewContent(
        **{
            "metadata": {
                "key": "orders-view",
                "name": "Orders View",
                "knowledgeModelKey": "orders-km",
            },
            "components": [
                {
                    "id": "published-table",
                    "type": "table",
                    "settings": {
                        "name": "Orders",
                        "dataSources": [
                            {
                                "id": "orders-source",
                                "attributes": [
                                    {
                                        "id": "order-id",
                                        "displayName": "Order ID",
                                        "pql": '"Orders"."ID"',
                                    }
                                ],
                            }
                        ],
                    },
                }
            ],
            "tabs": [],
        }
    )
    hydrated_view.get_content.return_value = view_content

    cf = CeloFast(
        "space-id",
        "package-id",
        mode="published",
        client=cast(Celonis, client),
    )
    first = cf.view("orders-view")
    second = cf.view("orders-view")
    different_variables = cf.view("orders-view", variables={"days": "7"})

    assert cf.mode == "published"
    assert cf.space is space
    assert cf.package is package
    assert first is second
    assert different_variables is not first
    assert first.table("published-table").to_query()["columns"] == {
        "Order ID": '"Orders"."ID"'
    }
    client.apps.get_space.assert_called_once_with("space-id")
    package.get_views.assert_called_once_with()
    package.get_view.assert_called_once_with("published-view-id")
    hydrated_view.get_content.assert_called_once_with()


def test_published_km_uses_canonical_root_key_and_apps_connector():
    client, _, _, _, get_content = make_published_client()
    cf = CeloFast(
        "space-id",
        "package-id",
        mode="published",
        client=cast(Celonis, client),
    )

    with patch("celofast.resolution.KnowledgeModel.get_content", get_content):
        handle = cf.km("orders-km")

    assert handle.native.root_with_key == "published-package-root.orders-km"
    assert handle.native.id == "published-package-root.orders-km"
    assert handle.mode == "published"
    assert handle._connector.draft is False
    get_content.assert_called_once_with()


def test_missing_published_km_is_mapped_to_resource_not_found():
    client, _, _, _, get_content = make_published_client(missing_km=True)
    cf = CeloFast(
        "space-id",
        "package-id",
        mode="published",
        client=cast(Celonis, client),
    )

    with patch("celofast.resolution.KnowledgeModel.get_content", get_content):
        with pytest.raises(ResourceNotFoundError, match="orders-km"):
            cf.km("orders-km")


def test_invalid_resource_mode_is_rejected_before_client_resolution():
    client = MagicMock()

    with pytest.raises(ValueError, match="mode"):
        CeloFast(
            "space-id",
            "package-id",
            mode="unsupported",  # type: ignore[arg-type]
            client=cast(Celonis, client),
        )

    client.apps.get_space.assert_not_called()
    client.studio.get_space.assert_not_called()
