"""Cached resolution of native PyCelonis Studio and Apps resources."""

from __future__ import annotations

from collections.abc import Sequence

from pycelonis.celonis import Celonis
from pycelonis.ems.apps.content_node.package import PublishedPackage
from pycelonis.ems.apps.content_node.view import PublishedView
from pycelonis.ems.apps.content_node.view.content import ViewContent
from pycelonis.ems.apps.space import PublishedSpace
from pycelonis.ems.data_integration.data_model import DataModel
from pycelonis.ems.studio.content_node.knowledge_model import KnowledgeModel
from pycelonis.ems.studio.content_node.package import Package
from pycelonis.ems.studio.content_node.view import View
from pycelonis.ems.studio.space import Space
from pycelonis_core.utils.errors import PyCelonisNotFoundError
from pydantic.v1 import ValidationError
import yaml

from celofast.exceptions import (
    ResourceAmbiguityError,
    ResourceNotFoundError,
    ResourceResolutionError,
    ViewContentError,
)
from celofast.types import ResourceMode


NativeSpace = Space | PublishedSpace
NativePackage = Package | PublishedPackage
NativeView = View | PublishedView


class _BaseResolver:
    """Shared caches and final KM/Data Model resolution for both contexts."""

    draft: bool
    space: NativeSpace
    package: NativePackage

    def __init__(self, client: Celonis) -> None:
        self.client = client
        self._view_content: dict[str, ViewContent] = {}
        self._knowledge_model_content: dict[str, object] = {}
        self._data_models: dict[str, DataModel] = {}
        self._data_models_loaded = False

    @staticmethod
    def _one_by_key(items: Sequence[object], kind: str, key: str):
        if not items:
            raise ResourceNotFoundError(
                f"{kind} with key {key!r} was not found in the configured package."
            )
        if len(items) > 1:
            raise ResourceAmbiguityError(
                f"More than one {kind} has key {key!r} in the configured package."
            )
        return items[0]

    def data_model(self, knowledge_model: KnowledgeModel) -> DataModel:
        """Resolve a KM's final Data Model and cache accessible pool models."""

        cache_key = knowledge_model.id
        if cache_key not in self._knowledge_model_content:
            try:
                content = knowledge_model.get_content()
            except PyCelonisNotFoundError as exc:
                if self.draft:
                    raise
                raise ResourceNotFoundError(
                    f"Knowledge Model with key {knowledge_model.key!r} was not "
                    "found in the published package."
                ) from exc
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


class StudioResolver(_BaseResolver):
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

    draft = True

    def __init__(self, client: Celonis, *, space_id: str, package_id: str) -> None:
        super().__init__(client)
        self.space_id = space_id
        self.package_id = package_id
        self.space: Space = client.studio.get_space(space_id)
        self.package: Package = self.space.get_package(package_id)

        self._knowledge_models: tuple[KnowledgeModel, ...] | None = None
        self._views: tuple[View, ...] | None = None
        self._knowledge_model_by_key: dict[str, KnowledgeModel] = {}
        self._view_by_key: dict[str, View] = {}

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

    def view_content(self, view: View) -> ViewContent:
        """Parse and validate serialized draft View content with PyCelonis."""

        if view.id in self._view_content:
            return self._view_content[view.id]
        if not view.serialized_content:
            raise ViewContentError(f"View {view.key!r} has no serialized Studio content.")
        try:
            payload = yaml.safe_load(view.serialized_content)
            if not isinstance(payload, dict):
                raise TypeError("serialized content must decode to a mapping")
            content = ViewContent(**payload)
            self._view_content[view.id] = content
            return content
        except (TypeError, yaml.YAMLError, ValidationError) as exc:
            raise ViewContentError(
                f"View {view.key!r} does not contain valid typed View content."
            ) from exc


class AppsResolver(_BaseResolver):
    """Resolve and cache native PyCelonis resources in a published Apps package.

    Published Apps packages do not expose Knowledge Models through an Apps
    collection.  The semantic-layer API addresses them by the package root
    key and KM key, so this resolver constructs the native PyCelonis
    ``KnowledgeModel`` reference from that canonical ``root_with_key``.
    """

    draft = False

    def __init__(self, client: Celonis, *, space_id: str, package_id: str) -> None:
        super().__init__(client)
        self.space_id = space_id
        self.package_id = package_id
        self.space: PublishedSpace = client.apps.get_space(space_id)
        self.package: PublishedPackage = self.space.get_package(package_id)
        self._views: tuple[PublishedView, ...] | None = None
        self._knowledge_model_by_key: dict[str, KnowledgeModel] = {}
        self._view_by_key: dict[str, PublishedView] = {}

    def knowledge_model(self, key: str) -> KnowledgeModel:
        """Build a native published KM reference from its exact key."""

        if key in self._knowledge_model_by_key:
            return self._knowledge_model_by_key[key]

        root_node_key = getattr(self.package, "root_node_key", None)
        space_id = getattr(self.package, "space_id", self.space_id)
        package_client = getattr(self.package, "client", None)
        if not all(isinstance(value, str) and value for value in (root_node_key, space_id)):
            raise ResourceResolutionError(
                "Published Package does not expose the root key required to "
                f"resolve Knowledge Model {key!r}."
            )
        if package_client is None:
            raise ResourceResolutionError(
                "Published Package does not expose its native PyCelonis client."
            )

        root_with_key = f"{root_node_key}.{key}"
        knowledge_model = KnowledgeModel(
            client=package_client,
            id=root_with_key,
            key=key,
            root_node_key=root_node_key,
            root_with_key=root_with_key,
            space_id=space_id,
        )
        self._knowledge_model_by_key[key] = knowledge_model
        return knowledge_model

    def view(self, key: str) -> PublishedView:
        """Find a published View by key and hydrate its final content."""

        if key in self._view_by_key:
            return self._view_by_key[key]
        if self._views is None:
            self._views = tuple(self.package.get_views())
        matches = [item for item in self._views if item.key == key]
        listed_view = self._one_by_key(matches, "View", key)
        if not listed_view.id:
            raise ResourceResolutionError(
                f"Published View {key!r} has no component ID for hydration."
            )
        view = self.package.get_view(listed_view.id)
        self._view_by_key[key] = view
        return view

    def view_content(self, view: PublishedView) -> ViewContent:
        """Return typed content fetched through ``PublishedView.get_content``."""

        if view.id in self._view_content:
            return self._view_content[view.id]
        try:
            content = view.get_content()
        except (TypeError, ValidationError) as exc:
            raise ViewContentError(
                f"View {view.key!r} does not contain valid typed View content."
            ) from exc
        if content is None:
            raise ViewContentError(
                f"View {view.key!r} has no published serialized content."
            )
        self._view_content[view.id] = content
        return content


def resolver_for(
    client: Celonis,
    *,
    space_id: str,
    package_id: str,
    mode: ResourceMode,
) -> StudioResolver | AppsResolver:
    """Construct the resolver for a validated resource mode."""

    if mode == "draft":
        return StudioResolver(client, space_id=space_id, package_id=package_id)
    if mode == "published":
        return AppsResolver(client, space_id=space_id, package_id=package_id)
    raise ValueError("mode must be either 'draft' or 'published'.")
