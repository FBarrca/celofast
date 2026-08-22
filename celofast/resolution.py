"""Cached resolution of native PyCelonis Studio resources."""

from __future__ import annotations

from pycelonis.celonis import Celonis
from pycelonis.ems.data_integration.data_model import DataModel
from pycelonis.ems.studio.content_node.knowledge_model import KnowledgeModel
from pycelonis.ems.studio.content_node.package import Package
from pycelonis.ems.studio.content_node.view import View
from pycelonis.ems.studio.space import Space

from celofast.exceptions import (
    ResourceAmbiguityError,
    ResourceNotFoundError,
    ResourceResolutionError,
)


class StudioResolver:
    """Resolve and cache native resources within one Studio draft package.

    The resolver is an internal package-scoped service used by
    :class:`celofast.CeloFast`.  It resolves the Space and Package once,
    lazily loads KM/View collections, and scans accessible Data Pools only
    when a KM's final content identifies a Data Model.  It deliberately uses
    PyCelonis collections and ``KnowledgeModel.get_content()`` instead of
    parsing Studio YAML or reimplementing package-variable semantics.

    Args:
        client: Authenticated native PyCelonis client.
        space_id: Studio Space ID.
        package_id: Studio Package ID within ``space_id``.
    """

    def __init__(self, client: Celonis, *, space_id: str, package_id: str) -> None:
        self.client = client
        self.space_id = space_id
        self.package_id = package_id
        self.space: Space = client.studio.get_space(space_id)
        self.package: Package = self.space.get_package(package_id)

        self._knowledge_models: tuple[KnowledgeModel, ...] | None = None
        self._views: tuple[View, ...] | None = None
        self._knowledge_model_by_key: dict[str, KnowledgeModel] = {}
        self._view_by_key: dict[str, View] = {}
        self._knowledge_model_content: dict[str, object] = {}
        self._data_models: dict[str, DataModel] = {}
        self._data_models_loaded = False

    def knowledge_model(self, key: str) -> KnowledgeModel:
        """Return exactly one native Knowledge Model selected by key.

        Args:
            key: Exact Studio Knowledge Model key.

        Returns:
            The cached native Knowledge Model object.

        Raises:
            ResourceNotFoundError: If no matching KM exists in the Package.
            ResourceAmbiguityError: If more than one matching KM is returned.
        """

        if key in self._knowledge_model_by_key:
            return self._knowledge_model_by_key[key]
        if self._knowledge_models is None:
            self._knowledge_models = tuple(self.package.get_knowledge_models())
        matches = [item for item in self._knowledge_models if item.key == key]
        knowledge_model = self._one_by_key(matches, "Knowledge Model", key)
        self._knowledge_model_by_key[key] = knowledge_model
        return knowledge_model

    def view(self, key: str) -> View:
        """Return exactly one native Studio View selected by key.

        Args:
            key: Exact Studio View key.

        Returns:
            The cached native draft View object.  Serialized View content is
            parsed by ``CeloFast.view`` so this resolver remains focused on
            resource lookup.

        Raises:
            ResourceNotFoundError: If no matching View exists in the Package.
            ResourceAmbiguityError: If more than one matching View is returned.
        """

        if key in self._view_by_key:
            return self._view_by_key[key]
        if self._views is None:
            self._views = tuple(self.package.get_views())
        matches = [item for item in self._views if item.key == key]
        view = self._one_by_key(matches, "View", key)
        self._view_by_key[key] = view
        return view

    def data_model(self, knowledge_model: KnowledgeModel) -> DataModel:
        """Resolve a KM's final Data Model and cache accessible pool models.

        Args:
            knowledge_model: Native KM whose resolved content supplies the
                Data Model ID.

        Returns:
            The native Data Model matching ``knowledge_model.get_content()
            .data_model_id``.  The Data Pool inventory is scanned at most once
            per resolver and each discovered model is cached by ID.

        Raises:
            ResourceResolutionError: If final KM content is missing, has no
                resolved Data Model ID, or names a model unavailable in an
                accessible Data Pool.

        Notes:
            Server-side package-variable replacement is therefore preserved;
            raw KM YAML is never interpreted by CeloFast.
        """

        cache_key = knowledge_model.id
        if cache_key not in self._knowledge_model_content:
            content = knowledge_model.get_content()
            if content is None:
                raise ResourceResolutionError(
                    f"Knowledge Model {knowledge_model.key!r} has no final content."
                )
            self._knowledge_model_content[cache_key] = content
        else:
            content = self._knowledge_model_content[cache_key]

        data_model_id = getattr(content, "data_model_id", None)
        if not isinstance(data_model_id, str) or not data_model_id:
            raise ResourceResolutionError(
                f"Knowledge Model {knowledge_model.key!r} has no resolved Data Model ID."
            )

        if data_model_id not in self._data_models and not self._data_models_loaded:
            for data_pool in self.client.data_integration.get_data_pools():
                for data_model in data_pool.get_data_models():
                    self._data_models[data_model.id] = data_model
            self._data_models_loaded = True

        try:
            return self._data_models[data_model_id]
        except KeyError as exc:
            raise ResourceResolutionError(
                f"No accessible Data Pool contains Data Model {data_model_id!r} "
                f"used by Knowledge Model {knowledge_model.key!r}."
            ) from exc

    @staticmethod
    def _one_by_key(items: list[object], kind: str, key: str):
        if not items:
            raise ResourceNotFoundError(
                f"{kind} with key {key!r} was not found in the configured package."
            )
        if len(items) > 1:
            raise ResourceAmbiguityError(
                f"More than one {kind} has key {key!r} in the configured package."
            )
        return items[0]
