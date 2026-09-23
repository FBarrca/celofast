"""Knowledge Model object clients over the native PyCelonis connector."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import TypeVar

import pandas as pd
from pycelonis.ems.data_integration.data_model import DataModel
from pycelonis.ems.studio.content_node.knowledge_model import KnowledgeModel
import pycelonis.pql as pql
from pycelonis.pql.saola_connector import KnowledgeModelSaolaConnector

from celofast.exceptions import ObjectValueError, QueryValidationError
from celofast.query import query_to_pql, validate_variables
from celofast.resources.augmentation_table import AugmentationTableCollection
from celofast.sdk.capture import Capture, Source
from celofast.sdk.definitions import Predicate, Related, Sort
from celofast.sdk.hydration import decode, hydrate
from celofast.sdk.objects import Object, ObjectCollection, ObjectModel
from celofast.sdk.planning import ReadPlan, plan_read, plan_values
from celofast.types import ResourceMode

O = TypeVar("O", bound=Object)
# Relationship predicates are resolved to value lists before the object read.
MAX_RELATED_VALUES = 10_000


class KnowledgeModelConnection:
    """Resolved native Knowledge Model resources and private export transport.

    Args:
        knowledge_model: Native PyCelonis Knowledge Model object.  In
            published mode this is a read-only final-layer reference created
            from the Apps package root key and KM key.
        data_model: Native Data Model resolved from the KM's final content.
        draft: Whether exports target the Studio draft; ``False`` for Apps.
        augmentation_tables: Optional shared augmentation-table collection.
        source: Verified KM identity, if available from native content.
        capture_loader: Lazy provenance retrieval used when generated
            definitions require verification and native content omitted it.

    The connection has no public query methods. Object clients and View tables
    use its private export path; ``native`` and ``data_model`` remain escape
    hatches to PyCelonis.
    """

    def __init__(
        self,
        knowledge_model: KnowledgeModel,
        data_model: DataModel,
        *,
        draft: bool = True,
        augmentation_tables: AugmentationTableCollection | None = None,
        source: Source | None = None,
        capture_loader: Callable[[], Capture] | None = None,
    ) -> None:
        self._native = knowledge_model
        self._data_model = data_model
        self._draft = draft
        self._augmentation_tables = augmentation_tables
        self._source = source
        self._capture_loader = capture_loader
        self._connector = KnowledgeModelSaolaConnector(
            data_model,
            knowledge_model,
            draft=draft,
        )

    def _validate_capture(self, capture: Capture) -> None:
        if self._source is None and self._capture_loader is not None:
            current = self._capture_loader()
            if current.definition.get("dataModelId") != self._data_model.id:
                raise QueryValidationError("Connected KM targets a different Data Model.")
            self._source = current.source
        if self._source is None or capture.source != self._source:
            raise QueryValidationError(
                "Generated model belongs to a different KM source or the source is unverified."
            )
        if capture.definition.get("dataModelId") != self._data_model.id:
            raise QueryValidationError("Generated model targets a different Data Model.")

    @property
    def mode(self) -> ResourceMode:
        """Return the lifecycle context used for KM exports."""
        return "draft" if self._draft else "published"

    @property
    def native(self) -> KnowledgeModel:
        """Return the underlying native PyCelonis Knowledge Model."""
        return self._native

    @property
    def data_model(self) -> DataModel:
        """Return the Data Model resolved from the KM's final content."""
        return self._data_model

    @property
    def augmentation_tables(self) -> AugmentationTableCollection:
        """Return Data Model-backed augmentation-table output operations.

        Warning:
            Augmentation tables are not KM resources. Mutations write to the
            shared underlying Data Model and can affect every KM or View that
            consumes it.
        """
        if self._augmentation_tables is None:
            self._augmentation_tables = AugmentationTableCollection(self._data_model)
        return self._augmentation_tables

    def _export(
        self,
        query: pql.PQL,
        *,
        limit: int | None = None,
        offset: int | None = None,
        distinct: bool = False,
    ) -> pd.DataFrame:
        # The DataFrame is a transport detail; native errors propagate unchanged.
        frame = pql.DataFrame.from_pql(query, saola_connector=self._connector)
        return frame.to_pandas(limit=limit, offset=offset, distinct=distinct)

    def _execute(
        self,
        query: Mapping[str, object],
        *,
        variables: Mapping[str, str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        distinct: bool = False,
    ) -> pd.DataFrame:
        """Export a View table query; not part of the Knowledge Model SDK."""
        for name, value in (("limit", limit), ("offset", offset)):
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise QueryValidationError(f"{name} must be a non-negative integer or None.")
        if not isinstance(distinct, bool):
            raise QueryValidationError("distinct must be a boolean.")
        native_query = query_to_pql(query, variables=variables)
        return self._export(native_query, limit=limit, offset=offset, distinct=distinct)


def _plain(value: object) -> object:
    """Convert one pandas/numpy cell into a plain Python value or None."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    item = getattr(value, "item", None)
    return item() if callable(item) and type(value).__module__ == "numpy" else value


def _rows(frame: pd.DataFrame, columns: Sequence[str]) -> Iterator[tuple[object, ...]]:
    if list(frame.columns) != list(columns):
        raise ObjectValueError(
            f"Export returned columns {list(frame.columns)!r}, expected {list(columns)!r}."
        )
    for row in frame.itertuples(index=False, name=None):
        yield tuple(_plain(value) for value in row)


def _native(plan: ReadPlan) -> pql.PQL:
    return pql.PQL(
        columns=[pql.PQLColumn(name=alias, query=query) for alias, query in plan.columns],
        filters=[pql.PQLFilter(query=query) for query in plan.filters],
        order_by_columns=[
            pql.OrderByColumn(query=query, ascending=ascending)
            for query, ascending in plan.order_by
        ],
    )


class KnowledgeModelClient:
    """Retrieve generated business objects from one connected Knowledge Model.

    Obtain it with ``cf.km(generated_model)``. Every read loads complete,
    validated objects; there is no column selection or tabular result.

    Example:
        >>> from generated.inventory import Plant, km as inventory
        >>> client = cf.km(inventory)
        >>> plant = client.objects(Plant).get("PLANT-1000")
    """

    def __init__(
        self,
        connection: KnowledgeModelConnection,
        model: ObjectModel,
        *,
        variables: Mapping[str, str] | None = None,
    ) -> None:
        connection._validate_capture(model.capture)
        self._connection = connection
        self._model = model
        self._variables = validate_variables(variables)

    @property
    def model(self) -> ObjectModel:
        """The generated object registry this client serves."""
        return self._model

    def objects(self, object_type: type[O]) -> ObjectCollection[O]:
        """Return all objects of one generated type, ready to filter or fetch."""
        if not isinstance(object_type, type) or object_type not in self._model.objects:
            raise QueryValidationError(
                f"{object_type!r} is not an object type of this generated model; "
                "import it from the same generated package that was passed to cf.km()."
            )
        return ObjectCollection(self, object_type)

    def _read(
        self,
        object_type: type[O],
        predicates: tuple[Predicate, ...],
        order: tuple[Sort, ...],
        *,
        limit: int,
        offset: int,
    ) -> list[O]:
        resolved: dict[int, list[object]] = {}

        def resolve(related: Related) -> list[object]:
            # Each relationship predicate is resolved once per read; nested
            # relations resolve recursively before their parent.
            if id(related) not in resolved:
                resolved[id(related)] = self._related_values(related, resolve)
            return resolved[id(related)]

        plan = plan_read(
            object_type.fields, predicates, order, variables=self._variables, resolve=resolve
        )
        # Distinct rows collapse repeated identical objects; conflicts remain
        # visible to hydration, which rejects them.
        frame = self._connection._export(_native(plan), limit=limit, offset=offset, distinct=True)
        rows = _rows(frame, [alias for alias, _ in plan.columns])
        return hydrate(object_type, rows, context=self)

    def _related_values(
        self, related: Related, resolve: Callable[[Related], list[object]]
    ) -> list[object]:
        plan = plan_values(
            related.target, related.predicate, variables=self._variables, resolve=resolve
        )
        frame = self._connection._export(
            _native(plan), limit=MAX_RELATED_VALUES + 1, distinct=True
        )
        values = [decode(related.target, row[0]) for row in _rows(frame, ["v"])]
        if len(values) > MAX_RELATED_VALUES:
            raise QueryValidationError(
                f"Relation {related.link!r} matched more than {MAX_RELATED_VALUES:,} related "
                "objects; add conditions to its predicate to narrow it."
            )
        return values

    @property
    def mode(self) -> ResourceMode:
        return self._connection.mode

    @property
    def native(self) -> KnowledgeModel:
        return self._connection.native

    @property
    def data_model(self) -> DataModel:
        return self._connection.data_model

    @property
    def augmentation_tables(self) -> AugmentationTableCollection:
        return self._connection.augmentation_tables

    def __repr__(self) -> str:
        return f"KnowledgeModelClient({self._model.source.key!r}, mode={self.mode!r})"


__all__ = ["KnowledgeModelClient", "KnowledgeModelConnection"]
