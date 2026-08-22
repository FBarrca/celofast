"""Native PyCelonis-backed resource handles."""

from celofast.resources.augmentation_table import (
    AugmentationTableCollection,
    AugmentationTableHandle,
)
from celofast.resources.knowledge_model import KnowledgeModelHandle
from celofast.resources.view import ViewHandle, ViewTableHandle

__all__ = [
    "AugmentationTableCollection",
    "AugmentationTableHandle",
    "KnowledgeModelHandle",
    "ViewHandle",
    "ViewTableHandle",
]
