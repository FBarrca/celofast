"""Reusable Knowledge Model queries backed by pycelonis and SaolaPy."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
from celofast.services.clients import get_celonis
from pycelonis import pql
from pycelonis.pql.data_frame import DataFrame as PyCelonisDataFrame

from saolapy.pql.base import PQLColumn, PQL


class KnowledgeModelService:
    """Resolve a Knowledge Model and query its associated Data Model.

    ``knowledge_model`` uses the stable reference format
    ``space_id.package_id.knowledge_model_name``. Raw PQL columns are supplied
    as a mapping from output name to PQL expression.
    """

    def __init__(self, knowledge_model: str, celonis: Any | None = None):
        self.knowledge_model_reference = knowledge_model
        self.celonis = celonis or get_celonis()
        self.knowledge_model = self._find_knowledge_model(knowledge_model)
        self.data_model = self._find_data_model()

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

    def _find_knowledge_model(self, reference: str) -> Any:
        try:
            space_id, package_id, knowledge_model_name = reference.split(".", 2)
        except ValueError as exc:
            raise ValueError(
                "knowledge_model must be `space_id.package_id.knowledge_model_name`."
            ) from exc

        space = self.celonis.studio.get_space(space_id)
        package = space.get_package(package_id)
        try:
            return next(
                knowledge_model
                for knowledge_model in package.get_knowledge_models()
                if knowledge_model.name == knowledge_model_name
            )
        except StopIteration as exc:
            raise LookupError(
                f"Knowledge Model `{knowledge_model_name}` was not found in package `{package_id}`."
            ) from exc

    def _find_data_model(self) -> Any:
        content = self.knowledge_model.get_content()
        data_model_id = content.data_model_id if content is not None else None
        if not data_model_id:
            raise RuntimeError(
                f"Knowledge Model `{self.knowledge_model_reference}` has no associated data model."
            )

        try:
            return next(
                data_model
                for data_pool in self.celonis.data_integration.get_data_pools()
                for data_model in data_pool.get_data_models()
                if data_model.id == data_model_id
            )
        except StopIteration as exc:
            raise LookupError(f"Data Model `{data_model_id}` was not found.") from exc
