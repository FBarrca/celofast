"""PyCelonis-native MLWB input queries and augmentation-table outputs."""

from dotenv import load_dotenv

load_dotenv()

from celofast.client import get_celonis
from celofast.core import CeloFast
from celofast.exceptions import (
    AmbiguousTableError,
    AugmentationValidationError,
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
from celofast.resources.augmentation_table import (
    AugmentationTableCollection,
    AugmentationTableHandle,
)
from celofast.types import ResourceMode

__all__ = [
    "AmbiguousTableError",
    "AugmentationTableCollection",
    "AugmentationTableHandle",
    "AugmentationValidationError",
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
