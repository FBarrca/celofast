"""Unified package-scoped entry point for Celofast."""

from __future__ import annotations

from collections.abc import Mapping

from pycelonis.celonis import Celonis

from celofast.client import get_celonis
from celofast.query import validate_variables
from celofast.resolution import (
    NativePackage,
    NativeSpace,
    resolver_for,
)
from celofast.resources.augmentation_table import AugmentationTableCollection
from celofast.resources.knowledge_model import KnowledgeModelHandle
from celofast.resources.view import ViewHandle
from celofast.types import ResourceMode


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
        >>> cf = CeloFast("space-id", "package-id")
        >>> km = cf.km("inventory-km-key")
        >>> frame = km.execute({"columns": {"Supplier": '"Vendor"."Name"'}})

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
        self._km_handles: dict[str, KnowledgeModelHandle] = {}
        self._augmentation_collections: dict[str, AugmentationTableCollection] = {}
        self._view_handles: dict[
            tuple[str, tuple[tuple[str, str], ...]], ViewHandle
        ] = {}

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

    def km(self, key: str) -> KnowledgeModelHandle:
        """Return a cached handle for a Knowledge Model selected by exact key.

        Args:
            key: Exact Knowledge Model key.  This is not the model's display
                name and is not interpreted as a package variable.  In
                published mode it is combined with the package root key to
                address the final semantic-layer model.

        Returns:
            A :class:`KnowledgeModelHandle` backed by the native PyCelonis
            Knowledge Model connector.  The associated Data Model is resolved
            from the KM's final server-side content, and the connector uses
            the selected lifecycle context.

        Raises:
            ResourceNotFoundError: If no KM with ``key`` exists in the Package.
            ResourceAmbiguityError: If the Package returns multiple matching
                KMs.
            ResourceResolutionError: If the KM has no accessible Data Model.
        """

        if key not in self._km_handles:
            native = self._resolver.knowledge_model(key)
            data_model = self._resolver.data_model(native)
            augmentation_tables = self._augmentation_collections.get(data_model.id)
            if augmentation_tables is None:
                augmentation_tables = AugmentationTableCollection(data_model)
                self._augmentation_collections[data_model.id] = augmentation_tables
            self._km_handles[key] = KnowledgeModelHandle(
                native,
                data_model,
                draft=self._resolver.draft,
                augmentation_tables=augmentation_tables,
            )
        return self._km_handles[key]

    def view(
        self,
        key: str,
        *,
        variables: Mapping[str, str] | None = None,
    ) -> ViewHandle:
        """Return a typed View handle selected by exact key.

        Args:
            key: Exact Studio/Apps View key, rather than a display name or ID.
            variables: Optional View input bindings.  Values are exact strings
                used for ``${name}`` substitutions in exported table queries.
                They are merged after published View input defaults and do not
                override server-managed Knowledge Model variables.

        Returns:
            A cached :class:`ViewHandle` exposing typed tables from root
            components and all View tabs.  Draft content is parsed from YAML;
            published content is fetched through ``PublishedView.get_content``.
            The associated KM and Data Model are resolved lazily when
            ``view.km`` or ``table.execute()`` needs them.  Exporting a table
            with ``table.to_query()`` only reads the native View component.

        Raises:
            ResourceNotFoundError: If no View with ``key`` exists in the
                configured Package.
            ResourceAmbiguityError: If multiple Views have that key.
            ViewContentError: If the View has no valid serialized typed
                ``ViewContent``.
            QueryValidationError: If ``variables`` is not a string mapping.
        """

        validated_variables = validate_variables(variables)
        variable_items = tuple(sorted(validated_variables.items()))
        cache_key = (key, variable_items)
        if cache_key in self._view_handles:
            return self._view_handles[cache_key]

        native = self._resolver.view(key)
        content = self._resolver.view_content(native)
        handle = ViewHandle(
            native,
            content,
            lambda: self.km(content.metadata.knowledge_model_key),
            variables=validated_variables,
        )
        self._view_handles[cache_key] = handle
        return handle
