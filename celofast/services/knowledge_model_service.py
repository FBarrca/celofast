"""Reusable Knowledge Model queries backed by pycelonis and SaolaPy."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
from celofast.services.clients import get_celonis
from celofast.studio.context import (
    resolve_knowledge_model_context,
    resolve_studio_context,
)
from pycelonis.pql.data_frame import DataFrame as PyCelonisDataFrame
from pycelonis.celonis import Celonis
from pycelonis.ems.data_integration.data_model import DataModel
from pycelonis.ems.studio.content_node.knowledge_model import KnowledgeModel

from saolapy.pql.base import PQLColumn, PQL


class KnowledgeModelService:
    """Query a Knowledge Model resolved from a Studio View or package key."""

    knowledge_model_reference: str
    celonis: Celonis
    knowledge_model: KnowledgeModel
    data_model: DataModel

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "Use KnowledgeModelService.from_studio(...) to construct this service."
        )

    @classmethod
    def from_studio(
        cls,
        celonis: Celonis | None = None,
        *,
        space_id: str,
        package_id: str,
        view_key: str | None = None,
        km_key: str | None = None,
        knowledge_model_key: str | None = None,
        data_model_id: str | None = None,
        data_pool_id: str | None = None,
    ) -> "KnowledgeModelService":
        """Construct a service from a published Studio View's context.

        Provide exactly one of ``view_key`` or ``km_key``. A View key resolves
        the Knowledge Model from the View's published metadata. A Knowledge
        Model key resolves the Knowledge Model directly from the package.
        """
        if (view_key is None) == (km_key is None):
            raise ValueError("Provide exactly one of view_key or km_key.")
        if km_key is not None and knowledge_model_key is not None:
            raise ValueError(
                "knowledge_model_key can only be used with view_key, not km_key."
            )

        client = get_celonis() if celonis is None else celonis
        if view_key is not None:
            context = resolve_studio_context(
                client,
                space_id=space_id,
                package_id=package_id,
                view_key=view_key,
                knowledge_model_key=knowledge_model_key,
                data_model_id=data_model_id,
                data_pool_id=data_pool_id,
            )
        else:
            assert km_key is not None
            context = resolve_knowledge_model_context(
                client,
                space_id=space_id,
                package_id=package_id,
                knowledge_model_key=km_key,
                data_model_id=data_model_id,
                data_pool_id=data_pool_id,
            )

        service = cls.__new__(cls)
        service.knowledge_model_reference = "{}.{}.{}".format(
            space_id,
            package_id,
            getattr(
                context.knowledge_model,
                "name",
                knowledge_model_key or "<resolved-from-view>",
            ),
        )
        service.celonis = client
        service.knowledge_model = context.knowledge_model
        service.data_model = context.data_model
        return service

    def query(self, attribute_columns: Mapping[str, str], limit: int | None = 10) -> pd.DataFrame:
        """Return selected attributes as a pandas DataFrame using SaolaPy."""
        if not attribute_columns:
            raise ValueError("attribute_columns must contain at least one column.")
        if limit is not None and limit < 0:
            raise ValueError("limit must be zero or greater, or None.")

        query = PQL(
            columns=[
                PQLColumn(name=name, query=expression)
                for name, expression in attribute_columns.items()
            ]
        )
        dataframe = PyCelonisDataFrame.from_pql(query, data_model=self.data_model)
        return dataframe.head(limit) if limit is not None else dataframe.to_pandas()
