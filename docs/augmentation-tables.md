# Augmentation tables

[Documentation](index.md) · [Views and inputs](views-and-inputs.md)

Use augmentation tables to store application results such as predictions,
scores, and operational decisions. Celofast exposes these operations through
the Data Model resolved from a KM.

## Platform reference and research notes

The detailed augmentation research is available in full:

- [Architecture and exact service limits](Augmentated_tables.md): the architecture
  diagram, PostgreSQL storage, join constraints, naming rules, numeric limits,
  and the original internal API and Compute documentation links.
- [Table-backed attributes, Annotation Builder, and migration](Augmentated_tables%20copy.md):
  TAA/V2 versus RAA/V1, primary keys and identifier tuples, native PyCelonis
  examples, runtime refresh behavior, Annotation Builder internals, value API
  endpoints, and migration requirements including `CELONIS_MIGRATION_ATTRIBUTE`.

These references retain their original content and sources. The sections below
explain how to use Celofast's table API.

## Understand the destination

An augmentation table is a **Data Model resource**. A generated record exposes
captured augmented attributes directly alongside its other fields. Their source
definitions remain in `record.metadata["augmentedAttributes"]`; they do not expose
the table's storage or a row-writing API. Creating a table does not
automatically create a corresponding attribute in the KM.

```text
Connected KM --> resolved Data Model --> augmentation table
                                            ^
                                            |
                                  application output rows
```

`mode="draft"` and `mode="published"` control which KM is resolved. They do
not create separate destinations for augmentation writes. A write can affect
every KM or View consuming the same underlying table.

The examples below perform real mutations when run. Replace the resource and
table names with your application's intended destination.

## Update an existing table

```python
import pandas as pd
from celofast import CeloFast

cf = CeloFast("SPACE_ID", "PACKAGE_ID")
km = cf.km("orders-km")

prediction_frame = pd.DataFrame({
    "ORDER_ID": ["PO-1001", "PO-1002"],
    "RISK_SCORE": [0.82, 0.14],
})

predictions = km.augmentation_tables.table(
    "ML_ORDER_PREDICTIONS",
    key="ORDER_ID",
)
predictions.upsert(prediction_frame)
```

`table()` returns a cached lazy reference. It does not check whether the remote
table exists; the first native operation reports a missing table. `upsert()`
uses the server-side primary key to insert new rows or update existing ones.
It does not add columns to the table's schema.

The optional `key` on `table()` is remembered for subsequent `remove()` calls.
It does not alter the remote primary key. Asking the same cached table handle
to remember a different key raises `AugmentationValidationError`.

## Create a table with initial rows

Use this alternative when the table has not been created yet. The initial
DataFrame must be non-empty; PyCelonis infers its schema from that frame.

```python
predictions = km.augmentation_tables.create(
    prediction_frame,
    table_name="ML_ORDER_PREDICTIONS",
    key="ORDER_ID",
    data_model_table_name="O_CELONIS_ORDER",
    foreign_key_columns=[("ORDER_ID", "ORDER_ID")],
)
```

| Argument | Meaning |
| --- | --- |
| `key` | One primary-key column in the augmentation DataFrame. |
| `data_model_table_name` | Existing regular Data Model table used as the join partner. |
| `foreign_key_columns` | Non-empty list of `(augmentation_column, data_model_column)` pairs. |

The primary key identifies an output row. The foreign-key mapping relates it
to a row in the regular table. They happen to use the same column in this
example, but have different roles. Supply values and column types compatible
with your destination schema and join.

Creation is explicit. Celofast does not implement "create if absent" or silently
replace an existing table. Native creation errors propagate to the caller.

## Remove rows or delete the table

To remove specific keys, supply a DataFrame containing those keys:

```python
obsolete = pd.DataFrame({"ORDER_ID": ["PO-1002"]})
predictions.remove(obsolete)
```

If the handle has no remembered key, pass it explicitly:

```python
table = km.augmentation_tables.table("OTHER_PREDICTIONS")
table.remove(pd.DataFrame({"ID": ["obsolete-id"]}), key="ID")
```

`remove()` removes rows. `predictions.delete()` permanently deletes the entire
remote augmentation table. After successful deletion, the collection forgets
that handle; obtain a fresh handle for a later table with the same name.

## Batches and failure behavior

Create, upsert, and remove use batches of at most **1,000 rows**. Override the
default with an integer `batch_size` from 1 to 1,000:

```python
predictions.upsert(prediction_frame, batch_size=500)
```

Creation sends the first batch through native table creation and the remaining
batches through native upserts. Calls stop at the first failed batch. There is
no transaction or automatic rollback across batches: after a failure, the
schema and earlier rows may already exist. Inspect the remote state before
deciding how your application should retry.

An empty upsert is a no-op. Empty removal is also a no-op when its key metadata
and key column are valid. Empty creation is rejected. Celofast does not mutate
the caller's DataFrame.

## Validation, access, and limits

Celofast checks DataFrame types, unique non-empty string column names, required
key/foreign-key columns for creation, required keys for removal, and batch
sizes. These failures raise `AugmentationValidationError`. Native schema,
permission, quota, and API failures retain their original exceptions.

The tenant must expose the augmentation API and grant the caller the relevant
Data Model write access. Service-level limits beyond Celofast's batching are
enforced by Celonis and can depend on the tenant/service version. The
[Compute 2.31.0 notes](Augmentated_tables.md#limitations) include exact constants
for table, column, row, identifier, string, and batch limits. They record a
100-table limit, while the [table-backed attribute reference](Augmentated_tables%20copy.md#limits-and-operating-guidance)
records 200 tables per Data Model. Both source contexts are preserved; check
which applies to your connected service before relying on either quota.

For native functionality, use `predictions.native` or `km.data_model`. See
[API reference](api-reference.md#augmentation-tables) for the complete public
surface and [Troubleshooting](troubleshooting.md) for failures.
