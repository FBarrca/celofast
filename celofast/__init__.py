"""Celofast public API; generated KM imports stay offline and lightweight."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from celofast.client import get_celonis
    from celofast.core import CeloFast
    from celofast.exceptions import (
        AmbiguousComponentError,
        AmbiguousTableError,
        AugmentationValidationError,
        CeloFastError,
        ComponentNotFoundError,
        ComponentVariableError,
        ObjectIdentityError,
        ObjectMappingError,
        ObjectNotFoundError,
        ObjectValueError,
        QueryValidationError,
        ResourceAmbiguityError,
        ResourceNotFoundError,
        ResourceResolutionError,
        TableNotFoundError,
        UnresolvedVariableError,
        ViewContentError,
    )
    from celofast.query import OrderByDefinition, QueryDefinition
    from celofast.resources.knowledge_model import KnowledgeModelClient
    from celofast.resources.augmentation_table import (
        AugmentationTableCollection,
        AugmentationTableHandle,
    )
    from celofast.resources.view_input import (
        CheckboxHandle,
        DatePickerHandle,
        DateRange,
        DropdownHandle,
        DropdownOption,
        InputBoxHandle,
        InputVariableValue,
        SelectorHandle,
    )
    from celofast.types import ResourceMode

__all__ = [
    "AmbiguousComponentError",
    "AmbiguousTableError",
    "AugmentationTableCollection",
    "AugmentationTableHandle",
    "AugmentationValidationError",
    "CeloFast",
    "CeloFastError",
    "CheckboxHandle",
    "ComponentNotFoundError",
    "ComponentVariableError",
    "DatePickerHandle",
    "DateRange",
    "DropdownHandle",
    "DropdownOption",
    "InputBoxHandle",
    "InputVariableValue",
    "KnowledgeModelClient",
    "ObjectIdentityError",
    "ObjectMappingError",
    "ObjectNotFoundError",
    "ObjectValueError",
    "OrderByDefinition",
    "QueryDefinition",
    "QueryValidationError",
    "ResourceAmbiguityError",
    "ResourceMode",
    "ResourceNotFoundError",
    "ResourceResolutionError",
    "SelectorHandle",
    "TableNotFoundError",
    "UnresolvedVariableError",
    "ViewContentError",
    "get_celonis",
]


_MODULES = {
    "get_celonis": "celofast.client",
    "CeloFast": "celofast.core",
    "OrderByDefinition": "celofast.query",
    "QueryDefinition": "celofast.query",
    "ResourceMode": "celofast.types",
    "KnowledgeModelClient": "celofast.resources.knowledge_model",
    "AugmentationTableCollection": "celofast.resources.augmentation_table",
    "AugmentationTableHandle": "celofast.resources.augmentation_table",
}
for _name in (
    "CheckboxHandle",
    "DatePickerHandle",
    "DateRange",
    "DropdownHandle",
    "DropdownOption",
    "InputBoxHandle",
    "InputVariableValue",
    "SelectorHandle",
):
    _MODULES[_name] = "celofast.resources.view_input"
for _name in __all__:
    _MODULES.setdefault(_name, "celofast.exceptions")


def __getattr__(name: str) -> Any:
    if name not in _MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(_MODULES[name]), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
