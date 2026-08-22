"""Reusable Celonis Knowledge Model services."""

from dotenv import load_dotenv

# Load local development configuration without overriding variables supplied by
# the shell or deployment environment.
load_dotenv()

from celofast.services.clients import get_celonis
from celofast.services.knowledge_model_service import KnowledgeModelService

__all__ = [
    "KnowledgeModelService",
    "get_celonis",
]
