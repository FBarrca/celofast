"""Typing contracts for PyCelonis objects consumed by the Studio reader."""

from collections.abc import Mapping
from typing import Any, Protocol, TypeAlias


class StudioViewLike(Protocol):
    """Minimum published-View interface required by the reader."""

    def json_dict(self) -> Mapping[str, Any]:
        """Return the PyCelonis JSON representation of the View."""

        ...


class SerializedContentLike(Protocol):
    """Object exposing serialized content without a full SDK model type."""

    serialized_content: Any


StudioContentLike: TypeAlias = StudioViewLike | SerializedContentLike
