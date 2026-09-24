"""Unified package-scoped entry point for Celofast."""

from __future__ import annotations

from pycelonis.celonis import Celonis

from celofast.client import get_celonis
from celofast.resolution import (
    NativePackage,
    NativeSpace,
    resolver_for,
)
from celofast.resources.augmentation_table import AugmentationTableCollection
from celofast.resources.knowledge_model import (
    KnowledgeModelClient,
    KnowledgeModelConnection,
)
from celofast.resources.view import ViewHandle
from celofast.types import ResourceMode
from celofast.exceptions import QueryValidationError
from celofast.sdk.objects import ObjectModel


class CeloFast:
    """Package-scoped entry point for Studio or published Apps resources.

    ``CeloFast`` fixes a Space, Package, and lifecycle mode for the lifetime
    of the object.  Knowledge Models and Views are then selected by their
    exact Studio/Apps ``key`` (not by a display name or ID), and resolved
    handles are cached so repeated lookups do not reload the same resource.

    Args:
        space_id: PyCelonis Studio Space ID.
        package_id: PyCelonis Package ID inside ``space_id``.
        mode: ``"draft"`` (the default) resolves through ``client.studio``;
            ``"published"`` resolves through ``client.apps`` and executes
            Knowledge Model exports against the published Apps context.
        client: Optional already-authenticated :class:`pycelonis.Celonis`
            client.  When omitted, :func:`celofast.get_celonis` creates one
            from the OAuth environment configuration.

    Raises:
        ValueError: If either identifier is empty.
        ResourceNotFoundError: If the Space or Package cannot be resolved.
        Exception: Native PyCelonis authentication or lookup failures are
            propagated with their original types and exception chains.

    Example:
        >>> from generated.inventory import Plant, km as inventory
        >>> cf = CeloFast("space-id", "package-id")
        >>> plant = cf.km(inventory).objects(Plant).get("PLANT-1000")

    Notes:
        The supplied client, Space, and Package are exposed as read-only
        properties for callers that need a native PyCelonis escape hatch.
        Published Apps packages do not expose Knowledge Models as an Apps
        collection; their native KM reference is constructed from the package
        root key and is intended for read-only final-layer queries.
    """

    def __init__(
        self,
        space_id: str,
        package_id: str,
        *,
        mode: ResourceMode = "draft",
        client: Celonis | None = None,
    ) -> None:
        """Create a resolver rooted at one Studio Space and Package.

        Resource collections are loaded lazily.  Constructing an instance
        therefore validates the identifiers and resolves the Space/Package,
        while Knowledge Model, View content, and Data Model work is deferred
        until the corresponding handle is requested.

        Args:
            space_id: Space ID accepted by the selected native client API.
            package_id: Package ID within the selected Space.
            mode: Resource lifecycle context, either ``"draft"`` or
                ``"published"``.
            client: Optional authenticated PyCelonis client.  Supplying one
                is useful for tests or when the application manages client
                authentication itself.

        Raises:
            ValueError: If ``space_id`` or ``package_id`` is blank.
            ResourceNotFoundError: If the IDs do not identify accessible
                Studio resources.
            Exception: Native client authentication or lookup failures are
                propagated unchanged.
        """
        if not space_id:
            raise ValueError("space_id must not be empty.")
        if not package_id:
            raise ValueError("package_id must not be empty.")
        if mode not in ("draft", "published"):
            raise ValueError("mode must be either 'draft' or 'published'.")

        self._client = client if client is not None else get_celonis()
        self._mode = mode
        self._resolver = resolver_for(
            self._client,
            space_id=space_id,
            package_id=package_id,
            mode=mode,
        )
        self._km_connections: dict[str, KnowledgeModelConnection] = {}
        self._augmentation_collections: dict[str, AugmentationTableCollection] = {}
        self._view_handles: dict[str, ViewHandle] = {}

    @property
    def client(self) -> Celonis:
        """Return the authenticated native PyCelonis client.

        Returns:
            The exact :class:`pycelonis.Celonis` instance used for resource
            resolution.  The property is read-only; use the native client
            APIs directly when functionality is outside CeloFast's scope.
        """
        return self._client

    @property
    def mode(self) -> ResourceMode:
        """Return the lifecycle mode used by this service.

        Returns:
            ``"draft"`` for Studio resources or ``"published"`` for Apps
            resources.
        """
        return self._mode

    @property
    def space(self) -> NativeSpace:
        """Return the configured native Studio or Apps Space.

        Returns:
            The resolved Studio :class:`Space` in draft mode or published
            Apps :class:`PublishedSpace` in published mode.
        """
        return self._resolver.space

    @property
    def package(self) -> NativePackage:
        """Return the configured native Studio or Apps Package.

        Returns:
            The resolved native Package object that owns this entry point's
            KMs and Views.
        """
        return self._resolver.package

    def km(self, model: ObjectModel) -> KnowledgeModelClient:
        """Return an object client for a generated Knowledge Model package.

        KM input variables used by generated fields are read from the KM on
        each read that needs them.

        Args:
            model: The ``km`` registry exported by a package generated with
                ``celofast km pull``. It stays offline and is never mutated.

        Returns:
            A :class:`KnowledgeModelClient` retrieving generated objects.

        Raises:
            TypeError: If ``model`` is not a generated object model.
            QueryValidationError: If the model targets another Space,
                Package, lifecycle, or Data Model.
        """

        if not isinstance(model, ObjectModel):
            raise TypeError(
                "cf.km() requires a generated object model, for example "
                "`from generated.inventory import km`. Run `celofast km pull` to "
                "generate one; KM keys and query definitions are no longer accepted."
            )
        expected = model.source
        if (expected.space_id, expected.package_id, expected.mode) != (
            self._resolver.space_id,
            self._resolver.package_id,
            self.mode,
        ):
            raise QueryValidationError(
                "Generated model targets a different Space, Package, or lifecycle."
            )
        return KnowledgeModelClient(self._km_connection(expected.key), model)

    def augmentation_tables(self, km_key: str) -> AugmentationTableCollection:
        """Return augmentation-table operations for the Data Model behind a KM.

        Args:
            km_key: Exact Studio/Apps Knowledge Model key used to locate its
                final Data Model. No generated package is required.
        """

        return self._km_connection(km_key).augmentation_tables

    def _km_connection(self, key: str) -> KnowledgeModelConnection:
        """Resolve and cache native KM resources by exact key."""

        if not isinstance(key, str) or not key:
            raise ValueError("Knowledge Model key must be a non-empty string.")
        if key not in self._km_connections:
            native = self._resolver.knowledge_model(key)
            data_model = self._resolver.data_model(native)
            augmentation_tables = self._augmentation_collections.get(data_model.id)
            if augmentation_tables is None:
                augmentation_tables = AugmentationTableCollection(data_model)
                self._augmentation_collections[data_model.id] = augmentation_tables
            self._km_connections[key] = KnowledgeModelConnection(
                native,
                data_model,
                draft=self._resolver.draft,
                augmentation_tables=augmentation_tables,
            )
        return self._km_connections[key]

    def view(self, key: str) -> ViewHandle:
        """Return the View with this exact key, cached per key.

        Draft content is parsed from the Studio View; published content is
        fetched from the Apps View. The View's Knowledge Model is resolved
        only when a table or data-backed dropdown runs a query.

        Raises:
            ResourceNotFoundError: If no View with ``key`` exists in the Package.
            ResourceAmbiguityError: If several Views have that key.
            ViewContentError: If the View has no valid typed content.
        """

        if key not in self._view_handles:
            native = self._resolver.view(key)
            content = self._resolver.view_content(native)
            km_key = content.metadata.knowledge_model_key
            self._view_handles[key] = ViewHandle(
                native,
                content,
                lambda: self._km_connection(km_key),
                lambda: self._resolver.knowledge_model(km_key),
            )
        return self._view_handles[key]
