"""Knowledge Model object clients over the native PyCelonis connector."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import TypeVar

import pandas as pd
from pycelonis.ems.data_integration.data_model import DataModel
from pycelonis.ems.studio.content_node.knowledge_model import KnowledgeModel
import pycelonis.pql as pql
from pycelonis.pql.saola_connector import KnowledgeModelSaolaConnector

from celofast.exceptions import ObjectValueError, QueryValidationError
from celofast.query import query_to_pql
from celofast.resources.augmentation_table import AugmentationTableCollection
from celofast.sdk.capture import input_variables
from celofast.sdk.definitions import Predicate, Sort
from celofast.sdk.expressions import bind_inputs
from celofast.sdk.hydration import ValueType, hydrate
from celofast.sdk.objects import Object, ObjectCollection, ObjectModel
from celofast.sdk.planning import plan_read
from celofast.types import ResourceMode

O = TypeVar("O", bound=Object)
logger = logging.getLogger("celofast.km")


class KnowledgeModelConnection:
    """Resolved native Knowledge Model resources and private export transport.

    Args:
        knowledge_model: Native PyCelonis Knowledge Model object.  In
            published mode this is a read-only final-layer reference created
            from the Apps package root key and KM key.
        data_model: Native Data Model resolved from the KM's final content.
        draft: Whether exports target the Studio draft; ``False`` for Apps.
        augmentation_tables: Optional shared augmentation-table collection.

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
    ) -> None:
        self._native = knowledge_model
        self._data_model = data_model
        self._draft = draft
        self._augmentation_tables = augmentation_tables
        self._connector = KnowledgeModelSaolaConnector(
            data_model,
            knowledge_model,
            draft=draft,
        )

    def _validate_model(self, model: ObjectModel) -> None:
        # Space, package, lifecycle, and KM key are checked when the connection
        # is chosen; the Data Model ID pins the tenant's actual data.
        if model.data_model_id != self._data_model.id:
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

    def _probe(self, expressions: Sequence[str], limit: int) -> list[tuple[object, ...]]:
        """Export expressions for a sample of rows; used to validate attributes at pull."""
        aliases = [f"c{index}" for index in range(len(expressions))]
        query = pql.PQL(
            columns=[pql.PQLColumn(name=alias, query=q) for alias, q in zip(aliases, expressions)]
        )
        return list(_rows(self._export(query, limit=limit), aliases))

    def _type_of(self, expression: str) -> ValueType | None:
        """Read the export schema, including for null values; never guess from rows."""
        import pyarrow as pa
        import pyarrow.parquet as parquet

        query = pql.PQL(columns=[pql.PQLColumn(name="value", query=expression)], limit=1)
        export = self._native._create_data_export(query, self._draft)
        export.wait_for_execution()
        for chunk in export.get_chunks():
            type_ = parquet.read_schema(chunk).field("value").type
            checks: tuple[tuple[Callable[..., bool], ValueType], ...] = (
                (pa.types.is_string, "str"), (pa.types.is_integer, "int"),
                (pa.types.is_floating, "float"), (pa.types.is_boolean, "bool"),
                (pa.types.is_timestamp, "datetime"), (pa.types.is_date, "date"),
            )
            return next((value for check, value in checks if check(type_)), None)
        return None


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


def _log_query(title: str, query: pql.PQL, *, limit: int, offset: int, names: Sequence[str]) -> None:
    """Log the exact PQL of one export at DEBUG level on ``celofast.km``."""
    if not logger.isEnabledFor(logging.DEBUG):
        return
    last = len(query.columns) - 1
    columns = "\n".join(
        f'    {column.query} AS "{column.name}"'
        + ("" if index == last else ",")
        + (f"  -- {names[index]}" if index < len(names) else "")
        for index, column in enumerate(query.columns)
    )
    lines = [f"{title} (limit={limit}, offset={offset}, distinct)", f"TABLE (\n{columns}\n)"]
    lines += [f.query for f in query.filters]
    if query.order_by_columns:
        lines.append("ORDER BY " + ", ".join(
            f"{o.query} {'ASC' if o.ascending else 'DESC'}" for o in query.order_by_columns
        ))
    logger.debug("\n".join(lines))


class KnowledgeModelClient:
    """Retrieve generated business objects from one connected Knowledge Model.

    Obtain it with ``cf.km(generated_model)``. Every read loads complete,
    validated objects; there is no column selection or tabular result.

    Example:
        >>> from generated.inventory import Plant, km as inventory
        >>> client = cf.km(inventory)
        >>> plant = client.objects(Plant).get("PLANT-1000")
    """

    def __init__(self, connection: KnowledgeModelConnection, model: ObjectModel) -> None:
        connection._validate_model(model)
        self._connection = connection
        self._model = model

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
        # KM input variables are read when the query needs them, once per read.
        current: dict[str, dict[str, str | None]] | None = None

        def value(name: str) -> str | None:
            nonlocal current
            if current is None:
                current = input_variables(self._connection.native)
            return current.get(name, {}).get("value")

        def bind(expression: str) -> str:
            return bind_inputs(expression, value, self._model.variables)

        # Relations render into this one query; every read is a single export.
        query = plan_read(object_type, predicates, order, bind=bind)
        names = [field.name for field in object_type.fields]
        _log_query(
            f"Read {object_type.fields.object_type} objects ({object_type.__name__})",
            query, limit=limit, offset=offset, names=names,
        )
        # Distinct rows collapse repeated identical objects; conflicts remain
        # visible to hydration, which rejects them.
        frame = self._connection._export(query, limit=limit, offset=offset, distinct=True)
        rows = _rows(frame, [column.name for column in query.columns])
        # Columns after the loaded fields exist only for sorting.
        return hydrate(object_type, (row[: len(names)] for row in rows), context=self)

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
