# Augmentation tables and Table Augmented Attributes

## Scope: what this project uses

This project targets **Augmentation Tables** themselves: special Data Model
tables whose rows can be created and changed through an API without running a
complete Data Model load. Exposing their columns in a Knowledge Model as
current **Table Augmented Attributes (TAA)**—also referred to as Knowledge
Model-level or V2 augmented attributes—is an optional downstream step. It is
not required to create or update the table through PyCelonis.

This is not the legacy **Record Augmented Attribute (RAA)** model. The word
“augmented” is used for both generations, so check the underlying object and
API rather than relying on the name alone.

> **In short:** an Augmentation Table stores the values; a Table Augmented
> Attribute exposes a table-backed column in the Knowledge Model. A legacy
> Record Augmented Attribute is configured on a Record through the older
> `augmentedAttributes` model.

## Terminology

| Term | Layer | Meaning |
| --- | --- | --- |
| **Augmentation Table** | Data Model / Compute | A mutable table joined to one regular Data Model table. Its schema and rows are managed through the Augmentation API. |
| **Table Augmented Attribute (TAA)** | Knowledge Model, current/V2 | An optional Knowledge Model-facing attribute backed by augmentation-table data. Current Annotation Builder outputs use this model. |
| **Record Augmented Attribute (RAA)** | Knowledge Model, legacy/V1 | The older attribute configured inside a Record's `augmentedAttributes` list. It uses record-scoped metadata and legacy value APIs. |

TAA and RAA address a similar business need—adding operational values to
loaded business data—but their identity, configuration, APIs, and lifecycle
are different.

## What an Augmentation Table is

An Augmentation Table is a special Data Model table designed for data that must
change more quickly than the normal Data Integration cycle. Typical values
include:

- machine-learning predictions and confidence scores;
- approvals, comments, and operational statuses;
- pricing or planning adjustments;
- Annotation Builder output; and
- calculated or curated values produced in Python.

The table can be created or dropped dynamically and its rows can be inserted,
updated, or deleted through the Augmentation API. A Data Model reload is not
required after each change.

### Structural properties

Every Augmentation Table has:

| Property | Purpose |
| --- | --- |
| Table name | Uniquely identifies the Augmentation Table in the Data Model. |
| Columns and data types | Define the values stored in the table. With PyCelonis, these come from the initial Pandas DataFrame. |
| Primary key | Identifies rows for upsert and deletion. The current PyCelonis creation method accepts one `key` column. |
| Join-partner table | The regular Data Model table being extended. |
| Foreign-key mapping | Maps one or more Augmentation Table columns to columns in the join-partner table. |

These are table and join properties. They are not the legacy RAA properties
such as `displayName`, `possibleValues`, or `defaultValue`.

### Relationship to regular Data Model tables

An Augmentation Table always participates in a constrained relationship:

- It is associated with exactly one regular Data Model table.
- The Augmentation Table is the fact/N-side of the relationship.
- The regular table is the dimension/one-side.
- An Augmentation Table cannot exist as the only table in a Data Model.
- An Augmentation Table cannot be joined to another Augmentation Table.
- A regular table can have multiple Augmentation Tables.

The foreign-key mapping defines how rows relate to the regular join-partner
table. Callers should supply compatible types, formats, and values. Current
Knowledge Model TAA value updates validate that the target Data Model row
exists; low-level table API behavior for unmatched values can depend on the
API version and should be verified before relying on it.

The primary key, foreign key, and Annotation Builder identifiers have different
roles:

- The **primary key** identifies a row inside the Augmentation Table. In the
  current PyCelonis API, `key` is one column.
- The **foreign-key mapping** defines the join to the regular table and can
  contain one or more column pairs.
- **Annotation Builder identifiers** identify input rows and are used by the
  generated output path to derive its augmentation key.

The examples below use `node_id` as both the primary key and foreign-key column
for simplicity; that is a modeling choice, not a general requirement. Because
the table is the N-side of the join, more than one augmentation row can relate
to one regular row.

If a consumer expects exactly one scalar TAA value per regular row, the full
foreign-key tuple must be unique across the Augmentation Table's rows. The
single-column PyCelonis `key` does not automatically enforce uniqueness of a
different or multi-column foreign-key tuple. Validate that tuple for uniqueness
before create and upsert operations, or choose a primary key that represents
the same one-row-per-join-partner invariant.

## How the current Knowledge Model attribute fits

A Table Augmented Attribute is the current Knowledge Model representation of
table-backed augmentation data. When that representation is configured, it
gives consumers an attribute they can query, filter, display, or edit while
Phoenix and Compute manage the underlying Augmentation Table values.

The layers are related but not interchangeable:

```text
Regular Data Model table
          1
          |
          N
Augmentation Table  <---- API or PyCelonis writes rows
          |
          v
Table Augmented Attribute (TAA/V2) in the Knowledge Model
          |
          v
Views, workflows, Annotation Builder, and PQL consumers
```

Creating an Augmentation Table through PyCelonis manages the Data Model
storage. Exposing its values as a Knowledge Model attribute is a separate,
optional metadata concern unless the calling feature, such as Annotation
Builder, creates and synchronizes both parts.

### TAA metadata is not table schema

Current TAA metadata can describe the Knowledge Model-facing identity and
presentation of the attribute, including its name, data type, default, and
choices. Annotation Builder creates v2 attribute metadata, tags AI-generated
attributes, and synchronizes choices for applicable outputs.

These properties live in the Knowledge Model metadata layer. They do not
change the physical Augmentation Table's name, primary key, join definition,
or column schema.

## PyCelonis lifecycle

The PyCelonis `DataModel` Augmentation API supports the complete table
lifecycle directly from ML Workbench or another Python environment:

| Operation | API | Result |
| --- | --- | --- |
| Create and initially load a table | `data_model.create_augmentation_table(...)` | Creates the schema, join, and initial rows. |
| Resolve an existing table | `data_model.get_augmentation_table(name)` | Returns an `AugmentationTable` handle. |
| Insert or update rows | `augmentation_table.upsert(df)` | Updates existing primary keys and inserts new ones. |
| Delete selected rows | `augmentation_table.remove(df, key)` | Removes rows identified by the supplied key values. |
| Delete the table | `augmentation_table.delete()` | Drops the complete table and its data. |

### Create an Augmentation Table

```python
import pandas as pd

predictions = pd.DataFrame(
    {
        # Match the type and format of o_celonis_MaterialMasterPlant.ID.
        "node_id": pd.Series(["node-1", "node-2"], dtype="string"),
        "stockout_probability": [0.12, 0.87],
        "prediction_label": ["STOCKED", "AT_RISK"],
    }
)

augmentation_table = data_model.create_augmentation_table(
    df=predictions,
    table_name="ML_StockoutPrediction",
    key="node_id",
    data_model_table_name="o_celonis_MaterialMasterPlant",
    foreign_key_columns=[
        ("node_id", "ID"),
    ],
)
```

`foreign_key_columns` contains pairs in the form
`(augmentation_table_column, regular_table_column)`. The initial DataFrame
supplies the table's columns, values, and Pandas data types.

### Upsert new and changed results

```python
latest_predictions = pd.DataFrame(
    {
        "node_id": pd.Series(["node-1", "node-3"], dtype="string"),
        "stockout_probability": [0.21, 0.94],
        "prediction_label": ["STOCKED", "AT_RISK"],
    }
)

augmentation_table = data_model.get_augmentation_table(
    "ML_StockoutPrediction"
)
augmentation_table.upsert(latest_predictions)
```

Here, `node-1` is updated and `node-3` is inserted. Upsert does not add
columns or change the schema; recreate or migrate the table when its schema
must change.

### Remove rows or delete the table

```python
rows_to_remove = pd.DataFrame(
    {
        "node_id": pd.Series(["node-2"], dtype="string"),
    }
)

augmentation_table.remove(rows_to_remove, key="node_id")

# Drop the complete Augmentation Table when it is no longer required.
augmentation_table.delete()
```

Deleting selected rows and dropping the complete table are different lifecycle
operations. Verify dependencies in the Knowledge Model before deleting a
table.

## Runtime and query behavior

The details in this section describe the supplied Celonis architecture context
and are implementation-specific. They should not be treated as a stable public
API contract across all platform versions.

Augmentation Table definitions and values are persisted in PostgreSQL. An API
write changes that operational store without triggering a normal Data Model
reload. The platform emits a corresponding change event through AMQP.

The PQL engine refreshes augmentation data lazily. It fetches the latest data
when:

1. a PQL query references the Augmentation Table; and
2. the table has changed since it was last queried.

Writes therefore do not require a Data Model reload. Accepted changes are made
available to PQL through lazy refresh when the changed table is next
referenced; no fixed visibility latency is promised here.

## How Annotation Builder uses Augmentation Tables

This section documents the supplied Annotation Builder architecture and its
current operational defaults. Naming, limits, and retry settings are
version-specific implementation details.

Annotation Builder's default `AUGMENTED` output mode uses the current table-
backed model:

- Each output column is represented as an Augmented Attribute v2 in the
  Knowledge Model.
- Values are written to Phoenix augmentation tables and keyed by the input-row
  identifiers.
- The lead table of the input PQL becomes the source table.
- Attribute names are sanitized from the output-column names.
- The generated table follows the pattern
  `{data_model_table}_AUG_{augmentation_table_name_suffix}`.
- The generated key column follows the pattern
  `{data_model_table}_{identifier_column_name}`.
- There is no separate deployment step. Accepted values are made available to
  PQL through the lazy refresh behavior described above.

Execution, test, and preview runs can create missing v2 attributes and update
their choices. Signal runs require the attributes to exist already because
automated runs do not have the user security context needed to create them.

Annotation Builder normalizes output before writing it. Text is truncated to
the configured maximum output length—500 characters in the supplied
architecture context—and choice outputs are matched against the declared
choices. Writes are buffered, rate-limited, and retried for transient `429`
and `503` responses.

## Do not confuse this with legacy Record Augmented Attributes

Legacy Record Augmented Attributes are configured in a Record's
`augmentedAttributes` list. Their configuration contains:

| Legacy RAA property | Meaning |
| --- | --- |
| `id` | Identifier of the Record Augmented Attribute. |
| `displayName` | User-facing name. |
| `possibleValues` | Optional allowed values. Updates outside this list are rejected. |
| `defaultValue` | Value used when no explicit value exists. It must belong to `possibleValues` when that list is set. |
| `columnType` | Data type of the attribute. |

The legacy platform generates a Record attribute with PQL so the value can be
queried and filtered. Values can be updated from workflows or directly from
supported Business Views components. Removing the configuration can remove
its generated backing table when no other Record uses that table.

Those behaviors belong to the legacy Record-level abstraction. They are not
the schema properties of an API-created Augmentation Table.

### Current table-backed model versus legacy record model

| Area | Augmentation Table, optionally exposed as TAA (current/V2) | Record Augmented Attribute (legacy/V1) |
| --- | --- | --- |
| Identity | Data Model table row, identified by typed key columns | Knowledge Model Record instance, identified by Record metadata and item ID |
| Storage definition | Table schema, primary key, join partner, foreign-key mapping | Record `augmentedAttributes` configuration |
| User-facing attribute | Table Augmented Attribute / Knowledge Model augmented attribute v2 | Generated Record attribute |
| Value API | Current single-value `/api/augmented-attributes/value` and batch `/api/augmented-attributes/values`; table lifecycle through the Augmentation API or PyCelonis | Legacy single-value `/api/augmented/attribute/value`, batch `/api/augmented/attribute/value/batch`, and batch-by-query APIs |
| Activity history | V2, bound to the Data Model table row | V1, bound to the legacy Record instance |
| New implementations | Target model for this project | Compatibility and migration only |

## Migrating legacy RAA to current TAA

When legacy Record Augmented Attributes must be migrated to Table Augmented
Attributes, the following rules apply.

In this section, an **identifier** is a logical tuple containing the values of
one or more identifier columns. A source RAA identifier tuple identifies the
legacy Record instance; a target TAA identifier tuple identifies the regular
Data Model row to which the target Augmentation Table will join.

### Required compatibility

- The source RAA and target TAA must have the same data type.
- Each source RAA identifier tuple must map to either one target TAA identifier
  tuple or no target tuple. One source tuple cannot map to multiple target
  tuples.

### Supported paths

- Migration within the same Knowledge Model is supported; the columns forming
  the target TAA identifier tuple do not need to match the columns forming the
  source RAA identifier tuple.
- Migration to a different Knowledge Model is supported, including when the
  target uses the same Data Model or a different Data Model.
- The target regular-table name may differ from the source regular-table name.
- The target regular table may introduce an identifier tuple containing one or
  more columns.
- No additional configuration is required when every column needed to
  reconstruct the source identifier tuple still exists separately in the
  target regular table.

### Renamed or missing identifier columns

If the source identifier tuple cannot be reconstructed from columns in the
target regular table, migration is supported only when the target identifier
tuple consists of a single column and that value can be queried from the
source table.

Create a Record attribute named `CELONIS_MIGRATION_ATTRIBUTE`
(case-insensitive) on the source Record. The migration uses it to query the
single target identifier value and map each source identifier tuple to a target
regular-table row. Values that do not identify a target row are not inserted
into the target Augmentation Table.

The migration is unsupported when the source Record cannot expose a
`CELONIS_MIGRATION_ATTRIBUTE` representing the target identifier.

## Limits and operating guidance

- A Data Model can contain at most **200 Augmentation Tables**.
- Additional limits apply to row count, table size, and number of columns.
  Requests fail when an Augmentation API limit is exceeded.
- Keep primary keys stable and foreign-key types aligned with the regular
  table.
- Keep the schema stable across upserts. Use a controlled migration for schema
  changes.
- Remove deprecated Annotation Builder outputs and other obsolete tables so
  they do not consume capacity.
- Treat table deletion as a dependency change: update or remove Knowledge
  Model attributes and consumers before dropping the table.

Annotation Builder tables that use older naming conventions may not be
deletable from the Knowledge Model interface. Re-run the Annotation Builder to
create output with the current naming convention, then manually remove the
outdated table.

## Further reading

- [Creating and using augmented attributes][augmented-attributes]
- [Configuring augmented attributes for legacy views][legacy-views]
- [Running an Annotation Builder][annotation-builder]
- [PyCelonis documentation][pycelonis]
- [Celonis 2026 release notes][release-notes]

[augmented-attributes]: https://docs.celonis.com/en/creating-and-using-augmented-attributes.html
[legacy-views]: https://docs.celonis.com/en/configuring-augmented-attributes-for-legacy-views.html
[annotation-builder]: https://docs.celonis.com/en/running-your-annotation-builder.html
[pycelonis]: https://celonis.github.io/pycelonis/latest/
[release-notes]: https://docs.celonis.com/en/2026-release-notes.html#UUID-84132151-c904-8f3b-15e2-a834c8ba1432_UUID-ced13560-3744-3326-3826-0aa11a2741ae
