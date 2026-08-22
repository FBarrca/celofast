"""Composable PQL resolvers for View variables and Knowledge Model references."""

import logging
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from pycelonis.ems.studio.content_node.knowledge_model import KnowledgeModel

from .exceptions import PqlResolutionError

LOGGER = logging.getLogger(__name__)
COMMENT_SPLIT_RE = re.compile(r"(--.*?$|/\*[\s\S]*?\*/)", re.MULTILINE)


def _transform_code_only(text: str, transform):
    """Apply ``transform`` to PQL code while leaving SQL comments untouched."""

    parts = COMMENT_SPLIT_RE.split(text)
    for index in range(0, len(parts), 2):
        parts[index] = transform(parts[index])
    return "".join(parts)


class VariableResolver:
    """Replace ``${name}`` placeholders with current View variable values."""

    VARIABLE_RE = re.compile(r"\$\{(\w+)\}")

    def __init__(self, variables: Mapping[str, Any]):
        self.variables = dict(variables)

    def resolve(self, pql: str) -> str:
        def replace(match):
            name = match.group(1)
            if name not in self.variables:
                raise PqlResolutionError(
                    "Unresolved PQL variable ${{{}}}. Supply it through variables or "
                    "define a readable default on the View.".format(name)
                )
            return str(self.variables[name])

        return _transform_code_only(pql, lambda code: self.VARIABLE_RE.sub(replace, code))


class KpiResolver:
    """Recursively expand ``KPI(...)`` references from a Knowledge Model."""

    KPI_RE = re.compile(
        r"KPI\(\s*[\"']?([^\"\')\s]+)[\"']?\s*\)",
        re.IGNORECASE,
    )

    def __init__(self, knowledge_model: KnowledgeModel, max_depth: int = 10):
        self.knowledge_model = knowledge_model
        self.max_depth = max_depth
        self._cache: Dict[str, Optional[str]] = {}

    def _formula(self, kpi_id: str) -> Optional[str]:
        if kpi_id not in self._cache:
            try:
                self._cache[kpi_id] = self.knowledge_model.get_kpi(kpi_id).pql
            except Exception:
                self._cache[kpi_id] = None
        return self._cache[kpi_id]

    def resolve(self, pql: str) -> str:
        text = pql
        for _ in range(self.max_depth):
            replaced = False

            def replace(match):
                nonlocal replaced
                kpi_id = match.group(1)
                formula = self._formula(kpi_id)
                if formula is None:
                    raise PqlResolutionError(
                        "KPI {!r} could not be resolved from the Knowledge Model.".format(kpi_id)
                    )
                replaced = True
                return "({})".format(formula)

            text = _transform_code_only(text, lambda code: self.KPI_RE.sub(replace, code))
            if not replaced:
                return text

        raise PqlResolutionError(
            "KPI expansion exceeded the maximum depth of {}.".format(self.max_depth)
        )


class RecordAttributeResolver:
    """Expand non-generated Knowledge Model record attributes recursively."""

    def __init__(self, knowledge_model: KnowledgeModel, max_depth: int = 5):
        self.max_depth = max_depth
        self._mappings: List[Tuple[re.Pattern, str]] = []

        content = knowledge_model.get_content()
        for record in getattr(content, "records", []):
            for attribute in getattr(record, "attributes", []):
                if getattr(attribute, "auto_generated", False):
                    continue
                replacement = getattr(attribute, "pql", None)
                if replacement is None:
                    LOGGER.warning(
                        "Skipping Knowledge Model attribute %s.%s because it has no PQL.",
                        getattr(record, "id", "?"),
                        getattr(attribute, "id", "?"),
                    )
                    continue
                source = '"{}"."{}"'.format(record.id, attribute.id)
                self._mappings.append((re.compile(re.escape(source), re.IGNORECASE), replacement))

    def resolve(self, pql: str) -> str:
        text = pql
        for _ in range(self.max_depth):
            replaced = False

            def transform(code):
                nonlocal replaced
                for pattern, replacement in self._mappings:
                    code, count = pattern.subn(replacement, code)
                    replaced = replaced or bool(count)
                return code

            text = _transform_code_only(text, transform)
            if not replaced:
                return text

        raise PqlResolutionError(
            "Record-attribute expansion exceeded the maximum depth of {}.".format(
                self.max_depth
            )
        )


class ResolverChain:
    """Apply multiple PQL resolvers in a deterministic order."""

    def __init__(self, resolvers: Iterable[Any]):
        self.resolvers = tuple(resolvers)

    def resolve(self, pql: str) -> str:
        resolved = pql
        for resolver in self.resolvers:
            resolved = resolver.resolve(resolved)
        return resolved


def default_resolver_chain(
    knowledge_model: KnowledgeModel, variables: Optional[Mapping[str, Any]] = None
) -> ResolverChain:
    """Build the same safe resolution order used by the original notebooks."""

    return ResolverChain(
        (
            KpiResolver(knowledge_model),
            RecordAttributeResolver(knowledge_model),
            VariableResolver(variables or {}),
        )
    )
