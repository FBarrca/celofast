"""Data Model-backed augmentation-table output handles."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence

import pandas as pd
from pycelonis.ems.data_integration.augmentation_table import AugmentationTable
from pycelonis.ems.data_integration.data_model import DataModel

from celofast.exceptions import AugmentationValidationError


MAX_AUGMENTATION_BATCH_SIZE = 1_000
"""Maximum rows sent by one augmentation-table mutation request."""


class AugmentationTableCollection:
    """Create and locate augmentation tables in one resolved Data Model.

    The collection is normally accessed through
    :attr:`KnowledgeModelHandle.augmentation_tables`. The Knowledge Model is
    only used to locate its final Data Model; all mutations happen directly at
    the Data Model layer and are not isolated by CeloFast's draft/published
    mode.

    Args:
        data_model: Native PyCelonis Data Model that owns the tables.

    Notes:
        :meth:`table` mirrors PyCelonis's lazy lookup: it constructs a native
        table reference but does not make a server request to verify that the
        table exists. Missing-table errors therefore surface on the first
        mutation.
    """

    def __init__(self, data_model: DataModel) -> None:
        self._data_model = data_model
        self._tables: dict[str, AugmentationTableHandle] = {}

    @property
    def data_model(self) -> DataModel:
        """Return the native Data Model owning these augmentation tables."""

        return self._data_model

    def table(
        self,
        table_name: str,
        *,
        key: str | None = None,
    ) -> "AugmentationTableHandle":
        """Return a cached lazy reference to an augmentation table.

        Args:
            table_name: Exact augmentation-table name in the Data Model.
            key: Optional primary-key column remembered by the returned handle.
                Supplying it lets :meth:`AugmentationTableHandle.remove` omit
                its per-call ``key`` argument.

        Returns:
            A cached :class:`AugmentationTableHandle` wrapping PyCelonis's
            native augmentation-table reference.

        Raises:
            AugmentationValidationError: If a name is empty or a cached handle
                was previously configured with a different primary key.

        Notes:
            This method does not verify remote existence. PyCelonis 2.15.1's
            ``DataModel.get_augmentation_table`` also creates a reference
            without issuing a lookup request.
        """

        name = _validate_name(table_name, field="table_name")
        validated_key = None if key is None else _validate_name(key, field="key")

        if name in self._tables:
            handle = self._tables[name]
            handle._remember_key(validated_key)
            return handle

        native = self._data_model.get_augmentation_table(name)
        handle = AugmentationTableHandle(
            native,
            self._data_model,
            key=validated_key,
            on_delete=self._forget,
        )
        self._tables[name] = handle
        return handle

    def create(
        self,
        df: pd.DataFrame,
        *,
        table_name: str,
        key: str,
        data_model_table_name: str,
        foreign_key_columns: Sequence[tuple[str, str]],
        batch_size: int = MAX_AUGMENTATION_BATCH_SIZE,
    ) -> "AugmentationTableHandle":
        """Create an augmentation table and populate it in bounded batches.

        The first batch is passed to PyCelonis
        ``DataModel.create_augmentation_table``, which creates the schema and
        upserts that batch. Remaining rows are sent through native ``upsert``
        calls. Column types are inferred by PyCelonis from the DataFrame.

        Args:
            df: Non-empty pandas DataFrame defining the schema and initial
                contents. The caller-owned frame is not mutated.
            table_name: Name of the new augmentation table.
            key: Primary-key column in ``df``.
            data_model_table_name: Regular Data Model table joined to the new
                augmentation table.
            foreign_key_columns: Non-empty pairs of ``(augmentation_column,
                data_model_column)`` describing the join.
            batch_size: Rows per create/upsert request. Must be between 1 and
                the service maximum of 1,000.

        Returns:
            A cached handle for the newly created table. It remembers ``key``
            for later remove operations.

        Raises:
            AugmentationValidationError: If local arguments are malformed or
                required DataFrame columns are absent.
            Exception: Native PyCelonis/API errors propagate unchanged.

        Notes:
            Creation is not transactional. PyCelonis creates the schema before
            its initial upsert, and CeloFast sends further batches separately;
            after a failure, the table or earlier rows may already exist.
        """

        frame = _validate_dataframe(df, allow_empty=False)
        name = _validate_name(table_name, field="table_name")
        primary_key = _validate_name(key, field="key")
        regular_table = _validate_name(
            data_model_table_name,
            field="data_model_table_name",
        )
        foreign_keys = _validate_foreign_keys(foreign_key_columns)
        size = _validate_batch_size(batch_size)

        if primary_key not in frame.columns:
            raise AugmentationValidationError(
                f"DataFrame must contain key column {primary_key!r}."
            )
        missing_foreign_keys = [
            augmentation_column
            for augmentation_column, _ in foreign_keys
            if augmentation_column not in frame.columns
        ]
        if missing_foreign_keys:
            rendered = ", ".join(repr(column) for column in missing_foreign_keys)
            raise AugmentationValidationError(
                f"DataFrame is missing augmentation foreign-key column(s): {rendered}."
            )

        batches = iter(_iter_batches(frame, size))
        first_batch = next(batches)
        native = self._data_model.create_augmentation_table(
            df=first_batch,
            table_name=name,
            key=primary_key,
            data_model_table_name=regular_table,
            foreign_key_columns=list(foreign_keys),
        )
        handle = AugmentationTableHandle(
            native,
            self._data_model,
            key=primary_key,
            on_delete=self._forget,
        )
        self._tables[name] = handle

        for batch in batches:
            native.upsert(batch)
        return handle

    def _forget(self, table_name: str, handle: "AugmentationTableHandle") -> None:
        if self._tables.get(table_name) is handle:
            del self._tables[table_name]


class AugmentationTableHandle:
    """Mutate one native PyCelonis augmentation table in bounded batches.

    The handle is a thin adapter over native ``upsert``, ``remove``, and
    ``delete`` operations. It adds local validation, optional remembered key
    metadata, and batching for the augmentation API's 1,000-row request limit.

    Augmentation tables are Data Model resources. A handle reached from a
    draft or published Knowledge Model writes to the same underlying Data
    Model and can affect every consumer of that table.
    """

    def __init__(
        self,
        table: AugmentationTable,
        data_model: DataModel,
        *,
        key: str | None = None,
        on_delete: Callable[[str, "AugmentationTableHandle"], None] | None = None,
    ) -> None:
        self._native = table
        self._data_model = data_model
        self._key = key
        self._on_delete = on_delete

    @property
    def name(self) -> str:
        """Return the exact native augmentation-table name."""

        return self._native.name

    @property
    def key(self) -> str | None:
        """Return the remembered primary-key column, if one was supplied."""

        return self._key

    @property
    def native(self) -> AugmentationTable:
        """Return the underlying native PyCelonis augmentation table."""

        return self._native

    @property
    def data_model(self) -> DataModel:
        """Return the native Data Model owning this augmentation table."""

        return self._data_model

    def upsert(
        self,
        df: pd.DataFrame,
        *,
        batch_size: int = MAX_AUGMENTATION_BATCH_SIZE,
    ) -> None:
        """Insert or update rows using native PyCelonis upserts.

        Args:
            df: pandas DataFrame containing rows to insert or update. Existing
                rows are matched using the table's server-side primary key.
            batch_size: Rows sent per request, from 1 through 1,000.

        Raises:
            AugmentationValidationError: If ``df`` or ``batch_size`` is invalid.
            Exception: Native PyCelonis/API errors propagate unchanged. Calls
                stop at the first failed batch and are not transactional.

        Notes:
            An empty DataFrame is a no-op. Native upsert cannot add columns to
            an existing augmentation table.
        """

        frame = _validate_dataframe(df)
        size = _validate_batch_size(batch_size)
        for batch in _iter_batches(frame, size):
            self._native.upsert(batch)

    def remove(
        self,
        df: pd.DataFrame,
        *,
        key: str | None = None,
        batch_size: int = MAX_AUGMENTATION_BATCH_SIZE,
    ) -> None:
        """Remove rows by their primary-key values.

        Args:
            df: pandas DataFrame containing the key values to remove.
            key: Primary-key column. It may be omitted when the handle was
                created by :meth:`AugmentationTableCollection.create` or
                configured through ``collection.table(name, key=...)``.
            batch_size: Rows sent per request, from 1 through 1,000.

        Raises:
            AugmentationValidationError: If no key is known, the key column is
                absent, or another local argument is invalid.
            Exception: Native PyCelonis/API errors propagate unchanged. Calls
                stop at the first failed batch and are not transactional.

        Notes:
            An empty DataFrame with a valid key column is a no-op.
        """

        frame = _validate_dataframe(df)
        resolved_key = self._key if key is None else _validate_name(key, field="key")
        if resolved_key is None:
            raise AugmentationValidationError(
                "key is required when the augmentation-table handle has no "
                "remembered primary key."
            )
        if self._key is not None and resolved_key != self._key:
            raise AugmentationValidationError(
                f"Augmentation table {self.name!r} is configured with key "
                f"{self._key!r}, not {resolved_key!r}."
            )
        if resolved_key not in frame.columns:
            raise AugmentationValidationError(
                f"DataFrame must contain key column {resolved_key!r}."
            )
        size = _validate_batch_size(batch_size)
        for batch in _iter_batches(frame, size):
            self._native.remove(batch, key=resolved_key)

    def delete(self) -> None:
        """Permanently delete the augmentation table through PyCelonis.

        Native errors propagate unchanged. The collection forgets this handle
        only after the server confirms deletion, so a subsequent ``table()``
        call constructs a fresh lazy reference.
        """

        self._native.delete()
        if self._on_delete is not None:
            self._on_delete(self.name, self)

    def _remember_key(self, key: str | None) -> None:
        if key is None:
            return
        if self._key is not None and self._key != key:
            raise AugmentationValidationError(
                f"Augmentation table {self.name!r} is already configured with "
                f"key {self._key!r}, not {key!r}."
            )
        self._key = key


def _validate_name(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AugmentationValidationError(f"{field} must be a non-empty string.")
    return value


def _validate_dataframe(
    df: object,
    *,
    allow_empty: bool = True,
) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame):
        raise AugmentationValidationError("df must be a pandas DataFrame.")
    if not allow_empty and df.empty:
        raise AugmentationValidationError("df must contain at least one row.")
    if not df.columns.is_unique:
        raise AugmentationValidationError("df column names must be unique.")
    invalid_columns = [
        column
        for column in df.columns
        if not isinstance(column, str) or not column.strip()
    ]
    if invalid_columns:
        raise AugmentationValidationError(
            "df column names must be non-empty strings."
        )
    return df


def _validate_foreign_keys(
    foreign_key_columns: object,
) -> tuple[tuple[str, str], ...]:
    if isinstance(foreign_key_columns, (str, bytes)) or not isinstance(
        foreign_key_columns,
        Sequence,
    ):
        raise AugmentationValidationError(
            "foreign_key_columns must be a non-empty sequence of column pairs."
        )
    if not foreign_key_columns:
        raise AugmentationValidationError(
            "foreign_key_columns must contain at least one column pair."
        )

    validated: list[tuple[str, str]] = []
    for index, pair in enumerate(foreign_key_columns):
        if isinstance(pair, (str, bytes)) or not isinstance(pair, Sequence):
            raise AugmentationValidationError(
                f"foreign_key_columns[{index}] must contain exactly two names."
            )
        if len(pair) != 2:
            raise AugmentationValidationError(
                f"foreign_key_columns[{index}] must contain exactly two names."
            )
        augmentation_column = _validate_name(
            pair[0],
            field=f"foreign_key_columns[{index}][0]",
        )
        data_model_column = _validate_name(
            pair[1],
            field=f"foreign_key_columns[{index}][1]",
        )
        validated.append((augmentation_column, data_model_column))
    return tuple(validated)


def _validate_batch_size(batch_size: object) -> int:
    if (
        not isinstance(batch_size, int)
        or isinstance(batch_size, bool)
        or not 1 <= batch_size <= MAX_AUGMENTATION_BATCH_SIZE
    ):
        raise AugmentationValidationError(
            "batch_size must be an integer between 1 and 1000."
        )
    return batch_size


def _iter_batches(df: pd.DataFrame, batch_size: int) -> Iterator[pd.DataFrame]:
    for start in range(0, len(df), batch_size):
        yield df.iloc[start : start + batch_size]
