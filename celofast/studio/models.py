"""Value objects representing the relevant parts of a Celonis View table."""

from dataclasses import dataclass, field
from typing import Any, Mapping, Tuple


@dataclass(frozen=True)
class ViewColumn:
    """One attribute configured on a table data source."""

    name: str
    pql: str
    hidden: bool = False
    referenced_entity: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ViewFilter:
    """One inline or Knowledge Model-backed filter configured on a table."""

    pql: str
    is_referenced: bool = False


@dataclass(frozen=True)
class ViewTable:
    """Parsed definition of a named table component in a Studio View."""

    name: str
    columns: Tuple[ViewColumn, ...]
    filters: Tuple[ViewFilter, ...]
