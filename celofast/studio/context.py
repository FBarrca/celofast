"""Resolve the Celonis objects needed by the View reader."""

import re
from dataclasses import dataclass
from typing import Any, Optional

from .exceptions import ContextResolutionError
from .parser import load_serialized_content

DATA_MODEL_VARIABLE_RE = re.compile(r"\$\{\{\s*([A-Za-z0-9_]+)\s*\}\}")


@dataclass(frozen=True)
class StudioContext:
    """Resolved Celonis objects used to parse and execute a View table."""

    view: Any
    knowledge_model: Any
    data_model: Any
    package: Any
    data_pool: Any


def _find_by_key(collection, key):
    return collection.find(key, search_attribute="key")


def resolve_studio_context(
    celonis: Any,
    *,
    space_id: str,
    package_id: str,
    view_key: str,
    knowledge_model_key: Optional[str] = None,
    data_model_id: Optional[str] = None,
    data_pool_id: Optional[str] = None,
) -> StudioContext:
    """Resolve a View, Knowledge Model, Data Model, and Data Pool from Studio IDs.

    ``knowledge_model_key`` and ``data_model_id`` are optional because both are
    normally discoverable from the published View and Knowledge Model metadata.
    Explicit values remain useful for unusual package layouts.
    """

    try:
        space = celonis.studio.get_space(space_id)
        package = space.get_package(package_id)
        view = _find_by_key(package.get_content_nodes(), view_key)

        view_content = load_serialized_content(view)
        km_key = knowledge_model_key or view_content.get("metadata", {}).get(
            "knowledgeModelKey"
        )
        if not km_key:
            raise ContextResolutionError(
                "The published View does not identify a Knowledge Model."
            )
        knowledge_model = _find_by_key(package.get_knowledge_models(), km_key)

        resolved_data_model_id = data_model_id or _resolve_data_model_id(
            package, knowledge_model
        )
        data_pool = (
            celonis.data_integration.get_data_pool(data_pool_id)
            if data_pool_id
            else _find_data_pool(celonis, resolved_data_model_id)
        )
        data_model = data_pool.get_data_model(resolved_data_model_id)
    except ContextResolutionError:
        raise
    except Exception as exc:
        raise ContextResolutionError(
            "Could not resolve the Celonis Studio context: {}".format(exc)
        ) from exc

    return StudioContext(view, knowledge_model, data_model, package, data_pool)


def _resolve_data_model_id(package: Any, knowledge_model: Any) -> str:
    content = load_serialized_content(knowledge_model)
    data_model_reference = content.get("dataModelId")
    if not isinstance(data_model_reference, str) or not data_model_reference.strip():
        raise ContextResolutionError("The Knowledge Model has no Data Model assigned.")

    match = DATA_MODEL_VARIABLE_RE.fullmatch(data_model_reference.strip())
    if not match:
        return data_model_reference

    variable_key = match.group(1)
    try:
        value = package.get_variables().find(variable_key, "key").value
    except Exception as exc:
        raise ContextResolutionError(
            "Could not resolve Data Model package variable {!r}.".format(variable_key)
        ) from exc
    if not value:
        raise ContextResolutionError(
            "Data Model package variable {!r} is empty.".format(variable_key)
        )
    return value


def _find_data_pool(celonis: Any, data_model_id: str):
    for data_pool in celonis.data_integration.get_data_pools():
        if any(model.id == data_model_id for model in data_pool.get_data_models()):
            return data_pool
    raise ContextResolutionError(
        "No Data Pool contains Data Model {!r}.".format(data_model_id)
    )


def read_view_variables(view: Any):
    """Read API-visible View input-variable defaults as ``{key: value}``."""

    definitions = getattr(view, "input_variable_definitions", None) or []
    variables = {}
    for definition in definitions:
        if isinstance(definition, dict):
            key = definition.get("key")
            value = definition.get("default_value", definition.get("defaultValue"))
        else:
            key = getattr(definition, "key", None)
            value = getattr(definition, "default_value", None)
        if key:
            variables[key] = value
    return variables
