"""Unified package-scoped entry point for Celofast."""

from __future__ import annotations

from collections.abc import Mapping

import yaml
from pycelonis.celonis import Celonis
from pycelonis.ems.apps.content_node.view.content import ViewContent
from pycelonis.ems.studio.content_node.package import Package
from pycelonis.ems.studio.space import Space
from pydantic.v1 import ValidationError

from celofast.client import get_celonis
from celofast.exceptions import ViewContentError
from celofast.query import validate_variables
from celofast.resolution import StudioResolver
from celofast.resources.knowledge_model import KnowledgeModelHandle
from celofast.resources.view import ViewHandle


class CeloFast:
    """Package-scoped entry point for PyCelonis Studio draft resources.

    ``CeloFast`` fixes the Studio Space and Package for the lifetime of the
    object.  Knowledge Models and Views are then selected by their exact
    Studio ``key`` (not by a display name or ID), and resolved handles are
    cached so repeated lookups do not reload the same resource.

    Args:
        space_id: PyCelonis Studio Space ID.
        package_id: PyCelonis Studio Package ID inside ``space_id``.
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
        This release targets Studio draft resources.  The supplied client,
        Space, and Package are exposed as read-only properties for callers
        that need a native PyCelonis escape hatch.
    """

    def __init__(
        self,
        space_id: str,
        package_id: str,
        *,
        client: Celonis | None = None,
    ) -> None:
        """Create a resolver rooted at one Studio Space and Package.

        Resource collections are loaded lazily.  Constructing an instance
        therefore validates the identifiers and resolves the Space/Package,
        while Knowledge Model, View content, and Data Model work is deferred
        until the corresponding handle is requested.

        Args:
            space_id: Studio Space ID, as accepted by ``client.studio``.
            package_id: Studio Package ID within the Space.
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

        self._client = client if client is not None else get_celonis()
        self._resolver = StudioResolver(
            self._client,
            space_id=space_id,
            package_id=package_id,
        )
        self._km_handles: dict[str, KnowledgeModelHandle] = {}
        self._view_handles: dict[
            tuple[str, tuple[tuple[str, str], ...]], ViewHandle
        ] = {}
        self._view_content: dict[str, ViewContent] = {}

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
    def space(self) -> Space:
        """Return the configured native Studio Space.

        Returns:
            The resolved :class:`pycelonis.ems.studio.space.Space` object.
        """
        return self._resolver.space

    @property
    def package(self) -> Package:
        """Return the configured native Studio Package.

        Returns:
            The resolved :class:`pycelonis.ems.studio.content_node.package.Package`
            object that owns this entry point's KMs and Views.
        """
        return self._resolver.package

    def km(self, key: str) -> KnowledgeModelHandle:
        """Return a cached handle for a Knowledge Model selected by exact key.

        Args:
            key: Exact Studio Knowledge Model key.  This is not the model's
                display name and is not interpreted as a package variable.

        Returns:
            A :class:`KnowledgeModelHandle` backed by the native PyCelonis
            Knowledge Model connector.  The associated Data Model is resolved
            from the KM's final server-side content.

        Raises:
            ResourceNotFoundError: If no KM with ``key`` exists in the Package.
            ResourceAmbiguityError: If the Package returns multiple matching
                KMs.
            ResourceResolutionError: If the KM has no accessible Data Model.
        """

        if key not in self._km_handles:
            native = self._resolver.knowledge_model(key)
            self._km_handles[key] = KnowledgeModelHandle(
                native,
                self._resolver.data_model(native),
            )
        return self._km_handles[key]

    def view(
        self,
        key: str,
        *,
        variables: Mapping[str, str] | None = None,
    ) -> ViewHandle:
        """Return a typed Studio draft View handle selected by exact key.

        Args:
            key: Exact Studio View key, rather than a display name or ID.
            variables: Optional View input bindings.  Values are exact strings
                used for ``${name}`` substitutions in exported table queries.
                They are merged after published View input defaults and do not
                override server-managed Knowledge Model variables.

        Returns:
            A cached :class:`ViewHandle` exposing typed tables from root
            components and all View tabs.  View content is parsed immediately,
            but its associated KM and Data Model are resolved lazily when
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
        if native.id not in self._view_content:
            if not native.serialized_content:
                raise ViewContentError(
                    f"View {key!r} has no serialized Studio content."
                )
            try:
                payload = yaml.safe_load(native.serialized_content)
                if not isinstance(payload, dict):
                    raise TypeError("serialized content must decode to a mapping")
                self._view_content[native.id] = ViewContent(**payload)
            except (TypeError, yaml.YAMLError, ValidationError) as exc:
                raise ViewContentError(
                    f"View {key!r} does not contain valid typed View content."
                ) from exc

        content = self._view_content[native.id]
        handle = ViewHandle(
            native,
            content,
            lambda: self.km(content.metadata.knowledge_model_key),
            variables=validated_variables,
        )
        self._view_handles[cache_key] = handle
        return handle
