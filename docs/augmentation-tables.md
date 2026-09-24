# Augmentation tables

[Documentation](index.md) · [Getting started](getting-started.md) · [API reference](api-reference.md)

Augmentation tables store your application's results, such as predictions,
scores, or decisions, in the Data Model behind a Knowledge Model. Add them to
the KM as augmented attributes, and the results appear next to the process
data in Studio and in your [KM objects](knowledge-model-sdk.md).

```python
import pandas as pd
from celofast import CeloFast

cf = CeloFast("SPACE_ID", "PACKAGE_ID")
tables = cf.augmentation_tables("orders-km")

predictions = tables.table("ML_ORDER_PREDICTIONS", key="ORDER_ID")
predictions.upsert(pd.DataFrame({
    "ORDER_ID": ["PO-1001", "PO-1002"],
    "RISK_SCORE": [0.82, 0.14],
}))
```

> **Writes are real and shared.** The examples on this page change data in
> Celonis. An augmentation table belongs to the Data Model, so a write is seen
> by every KM and View that uses it, in draft and published alike.

## Contents

1. [Find the tables](#1-find-the-tables)
2. [Create a table](#2-create-a-table)
3. [Write rows](#3-write-rows)
4. [Remove rows](#4-remove-rows)
5. [Delete a table](#5-delete-a-table)
6. [Write large DataFrames](#6-write-large-dataframes)
7. [Use the results in the KM](#7-use-the-results-in-the-km)
8. [Errors and limits](#8-errors-and-limits)

## 1. Find the tables

Name the KM whose Data Model holds the tables. No generated package is needed:

```python
tables = cf.augmentation_tables("orders-km")
```

A KM client offers the same: `cf.km(inventory).augmentation_tables`.

`tables.table(name)` returns a handle to one table. It doesn't check that the
table exists; the first write reports a missing table.

## 2. Create a table

Create a table from its first rows. Its columns and types come from the
DataFrame, which must not be empty:

```python
predictions = tables.create(
    prediction_frame,
    table_name="ML_ORDER_PREDICTIONS",
    key="ORDER_ID",                                # the primary key column
    data_model_table_name="O_CELONIS_ORDER",       # the process table it joins to
    foreign_key_columns=[("ORDER_ID", "ORDER_ID")],  # (this table's column, that table's column)
)
```

`key` identifies each row of your table. `foreign_key_columns` joins it to a
table of the Data Model, so each result belongs to an order. The two often use
the same column, as here.

`create()` fails if the table already exists; it never replaces one.

## 3. Write rows

`upsert()` adds new rows and updates existing ones, matched by the table's
primary key:

```python
predictions = tables.table("ML_ORDER_PREDICTIONS", key="ORDER_ID")
predictions.upsert(prediction_frame)
```

The DataFrame's columns must be the table's columns; `upsert()` can't add new
ones. An empty DataFrame writes nothing. Your DataFrame is never modified.

## 4. Remove rows

Pass a DataFrame with the keys of the rows to remove:

```python
predictions.remove(pd.DataFrame({"ORDER_ID": ["PO-1002"]}))
```

`remove()` uses the `key` given to `table()`. Without one, pass it:

```python
tables.table("OTHER_PREDICTIONS").remove(pd.DataFrame({"ID": ["obsolete-id"]}), key="ID")
```

## 5. Delete a table

```python
predictions.delete()
```

This permanently deletes the whole table and its rows. To use the name again,
create the table again.

## 6. Write large DataFrames

`create()`, `upsert()`, and `remove()` send rows in batches of up to 1,000.
Choose a smaller batch with `batch_size`:

```python
predictions.upsert(prediction_frame, batch_size=500)
```

A call stops at the first batch that fails, and batches already sent stay
written: there is no rollback. After a failure, check what's in the table
before retrying; `upsert()` is safe to repeat.

## 7. Use the results in the KM

Creating a table doesn't add anything to the KM. To see the results in Studio
and in your objects:

1. In Studio, add an augmented attribute to the KM record that the table joins
   to (for example, `RISK_SCORE` on the order record).
2. Pull the KM again: `uv run celofast km pull orders`. The attribute becomes
   a field of the generated class, like any other.

```python
order = client.objects(Order).get("PO-1001")
print(order.risk_score)
```

Later writes to the table show up on the next read; no pull is needed unless
you add attributes.

## 8. Errors and limits

| Error | Meaning |
| --- | --- |
| `AugmentationValidationError` | The DataFrame or arguments are invalid: not a DataFrame, empty or duplicate column names, a missing key or foreign-key column, or `batch_size` outside 1 to 1,000. Checked before anything is sent. |
| Native PyCelonis errors | Schema, permission, quota, and API failures from Celonis, raised unchanged. |

Your client needs write access to the Data Model. Celonis limits the number of
tables, columns, and rows, and the lengths of names and values; see the
[architecture and limit notes](Augmentated_tables.md) and the
[detailed platform reference](Augmentated_tables%20copy.md) for the exact
figures, which depend on the service version.

For native access, `predictions.native` is the PyCelonis augmentation table and
`tables.data_model` the Data Model. See also
[Troubleshooting](troubleshooting.md#augmentation-writes).
