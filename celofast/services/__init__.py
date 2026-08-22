"""Celonis Knowledge Model services."""

from celofast.services.clients import get_celonis
from celofast.services.knowledge_model_service import KnowledgeModelService

__all__ = [
    "KnowledgeModelService",
    "get_celonis",
]
