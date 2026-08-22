"""PyCelonis-native utilities for reusable KM and Studio View queries."""

from dotenv import load_dotenv

load_dotenv()

from celofast.client import get_celonis
from celofast.core import CeloFast
from celofast.exceptions import (
    AmbiguousTableError,
    CeloFastError,
    QueryValidationError,
    ResourceAmbiguityError,
    ResourceNotFoundError,
    ResourceResolutionError,
    TableNotFoundError,
    UnresolvedVariableError,
    ViewContentError,
)
from celofast.query import OrderByDefinition, QueryDefinition
from celofast.types import ResourceMode

__all__ = [
    "AmbiguousTableError",
    "CeloFast",
    "CeloFastError",
    "OrderByDefinition",
    "QueryDefinition",
    "QueryValidationError",
    "ResourceMode",
    "ResourceAmbiguityError",
    "ResourceNotFoundError",
    "ResourceResolutionError",
    "TableNotFoundError",
    "UnresolvedVariableError",
    "ViewContentError",
    "get_celonis",
]
