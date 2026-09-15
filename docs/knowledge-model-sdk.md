# Knowledge Models: typed definitions and small queries

[Documentation](index.md) · [Getting started](getting-started.md) · [API reference](api-reference.md) · [Migrating to 0.4](migration-0.4.md)

A KM handle executes queries and returns pandas DataFrames. Optional generated
objects provide autocomplete and captured business definitions.

After [configuring authentication](getting-started.md#2-configure-authentication),
you can query without generation:

```python
from celofast import CeloFast

cf = CeloFast("SPACE_ID", "PACKAGE_ID", mode="draft")
km = cf.km("inventory-km")
plants = km.select({"Plant number": '"Plant"."Number"'}).execute(limit=5)
```

Replace the IDs, key, and expressions with values from your tenant. The typed
examples below assume an Inventory KM with the illustrated records and fields.

## Configure and pull

To add autocomplete, register your KM in your application's `pyproject.toml`:

```toml
[tool.celofast.knowledge-models.inventory]
space-id = "SPACE_ID"
package-id = "PACKAGE_ID"
key = "inventory-km"
mode = "draft"
output = "generated/inventory"
```

```bash
uv run celofast km pull inventory
```

Or supply everything explicitly:

```bash
uv run celofast km pull --space-id SPACE_ID --package-id PACKAGE_ID --km inventory-km --mode draft --output generated/inventory
```

Configured output paths are relative to `pyproject.toml`; explicit `--output`
paths are relative to the working directory. `--project path/to/pyproject.toml`
selects another project configuration. Draft and published sources are separate.

## Import, explore, and query

```python
from generated.inventory import km as inventory

km = cf.km(inventory)
plant = inventory.records.o_celonis_plant
number = plant.number_formatted

number.id
number.description
number.column_type
number.pql
number.metadata

result = km.select({"Plant number": number}).execute(limit=100)
```

`inventory` always contains offline definitions. `km` is the cached execution
handle. Importing generated definitions does not load credentials, contact
Celonis, or import the PyCelonis query stack.

Generation exposes records, KPIs, filters, and a flat set of fields on each
record. Attributes from the source's `attributes`, `newAttributes`, and
`augmentedAttributes` collections all appear directly on the record. There are
no generated record collection fields or separate attribute-namespace classes.
Other categories, including variables, activities, actions, KPI parameters, and
unknown content, remain available through immutable `.metadata` mappings.

```python
for attribute in plant:
    print(attribute.id, attribute.description)

number = plant["NumberFormatted"]
field_count = len(plant)
original_attributes = plant.metadata.get("attributes", ())
variables = inventory.metadata.get("variables", ())
```

Generated fields have precise declared types when metadata provides them;
unknown types use `Any`. Record iteration and exact-ID lookup return
`Attribute[Any]`. These declarations do not guarantee pandas dtypes or non-null
result values. Iteration includes fields without PQL; query expansion skips them.

Generated records are frozen dataclasses with explicit business fields. For
example, a record declaration looks like this:

```python
@dataclass(frozen=True, kw_only=True)
class RecordsOCelonisPlant(Record):
    """Plant."""

    country: Attribute[str]
    plantnumber: Attribute[str]
```

This is an excerpt from generated source; applications import the ready-built
`km` object. A private builder constructs the hierarchy once at import. Repeated
navigation, iteration, and exact-ID lookup retain the same objects:

```python
assert plant is inventory.records.o_celonis_plant
assert plant["COUNTRY"] is plant.country  # Use the captured exact ID.
```

Fields cannot be reassigned. Construction uses memory for the complete captured
hierarchy upfront; accessing a field does not construct another wrapper.

### Collisions and source collections

Names that normalize to the same Python spelling, or collide with runtime
members such as `metadata` or `get_attribute`, receive readable suffixes:
`id_attribute` preserves `plant.id` for the record's own ID, and
`metadata_attribute` preserves `plant.metadata`. Collisions across source
collections use suffixes such as `_attribute`, `_new_attribute`, and
`_augmented_attribute`. A small numeric suffix resolves any remaining overlap;
natural names of other fields are preserved.
Every attribute still has a direct typed field; `schema.json` maps each original
source path to its generated field. For example, `plant["metadata"]` accesses a
business attribute while `plant.metadata` describes the record.

An exact ID can occur in multiple source collections. `plant["Shared"]` then
raises `KeyError`. Scope the lookup using the original source collection key:

```python
original = plant.get_attribute("Shared", collection="attributes")
added = plant.get_attribute("Shared", collection="newAttributes")
augmented = plant.get_attribute("Shared", collection="augmentedAttributes")
```

Missing IDs or no matching attribute in the selected collection also raise
`KeyError`. The original source path remains on `attribute.path`, and the full
source collections remain in `plant.metadata`.

### Select a complete record

```python
all_plants = km.select(plant)
active_plants = all_plants.where(inventory.filters.active_inventory)
plants = active_plants.where(plant.country.eq("DE")).execute(distinct=True)
```

Whole-record selection uses the source collections `attributes`, then `newAttributes`,
then `augmentedAttributes`, preserving captured order within each collection.
It includes attributes with non-empty IDs and PQL expressions. Output names
are exact attribute IDs. Unsupported categories and attributes without PQL
are skipped; duplicate IDs across collections and empty selections raise
`QueryValidationError`. Select explicit columns for custom aliases or subsets.

### Compose and reuse queries

```python
value = inventory.kpis.inventory_value
base = km.select(plant=plant.number_formatted, value=value)
active = base.where(inventory.filters.active_inventory)
largest = active.order_by(value.desc())

native_pql = largest.build()
result = largest.execute(limit=100)
query_dict = largest.to_query()
result = km.execute(query_dict, limit=100)
```

| Operation | Behavior |
| --- | --- |
| `km.select(record)` | Expand all queryable record attributes. |
| `km.select(**columns)` | Select with keyword output names. |
| `km.select({"Plant number": number})` | Select with arbitrary string output names. Mappings and keywords may be combined; duplicates fail. |
| `query.where(*filters)` | Append generated filters, equality predicates, or complete raw `FILTER ...;` statements, combined with AND. |
| `query.order_by(*expressions)` | Replace sorting. Plain expressions ascend; `.asc()` and `.desc()` choose direction. No arguments clears sorting. |
| `query.build(variables=...)` | Compile native PQL without exporting data. |
| `query.to_query()` | Return an independent Python dictionary retaining captured objects and their source information. |
| `query.execute(...)` | Fetch a DataFrame; accepts `variables`, `limit`, `offset`, and `distinct`. |

Queries are immutable: composing a branch leaves its base unchanged. Columns,
filters, and sorting can mix generated objects and raw PQL strings. `to_query()`
is not necessarily JSON serializable; use plain-string definitions when you
need JSON configuration. See [Dictionary queries](dictionary-queries.md).

Omitting `limit` requests all matching rows; use `limit=100` for a preview.
For pagination, choose suitable ordering and pass `limit`/`offset`. Data is live,
so concurrent changes can move rows between pages. `distinct=True` requests
distinct result rows without defining business-object identity.

### Attribute equality and raw filters

```python
query = (
    km.select(plant)
    .where(plant.country.eq("DE"))
    .where('FILTER "Plant"."Active" = 1;')
)
plants = query.execute(limit=100)
```

`.eq(value)` accepts strings, finite numbers, booleans, dates, datetimes, and
`None` (`IS NULL`). It escapes strings and encodes booleans as 1/0. Datetimes
use millisecond precision; timezone-aware values convert to UTC, and finer
precision is rejected. Static type checkers check the declared attribute type.

The attribute expression is bound before adding the encoded literal. Literal
`${name}` text is never treated as a variable replacement. Combine predicates
with repeated `where()` calls; Python `and`/`or` on a predicate raises
`QueryValidationError`. Write other comparisons as raw PQL filters.

### Validation and errors

Builder and dictionary queries share one compiler and execution path. Local
checks reject invalid shapes and categories, empty expressions, duplicate names,
incompatible captured sources, and invalid bindings or execution options.
Limits/offsets must be non-negative integers, excluding booleans; `distinct`
must be a boolean. Each execution compiles once and uses the native connector.

Celonis validates PQL grammar and dependencies during execution. `build()` does
not prove that a query is valid PQL. Native PyCelonis/SaolaPy errors propagate
unchanged with their original cause chains in both query styles.

### Connections and compatibility

`cf.km(inventory)` and `cf.km(inventory.key)` return the same cached
`KnowledgeModelHandle`. Generated roots have no connection state, query methods,
or native-resource properties. Use `km.native`, `km.data_model`, and
`km.augmentation_tables` for the corresponding resources.

Passing a generated root checks tenant, Space, Package, KM key, lifecycle, and
Data Model. Compilation also checks captured columns, filters, predicates, and
ordering; record selection checks source identity before expansion. A handle
with missing provenance retrieves it when typed objects first need verification.
Unverified or mismatched sources are rejected. Handles never store your imported
root, so queries can retain independent captures from the same source.

The flat record API uses runtime-v5 packages. Regenerate older packages with
`celofast km pull`, then restart Python. Replace `plant.attributes.country` with
`plant.country`, `for attribute in plant.attributes` with `for attribute in plant`,
and `plant.attributes["COUNTRY"]` with `plant["COUNTRY"]`. Use `get_attribute`
with a collection key when an ID is ambiguous. Older runtime packages are rejected
at import with a regeneration message.

## Native execution

### Captured input defaults

Pull retains Studio input-variable definitions for inspection:

```python
inventory.input_variables["im_consideredfuturemonths"]["defaultValue"]
```

This immutable mapping is included in captures, integrity checks, and drift
reports. It describes declared defaults, not current View input values.
An empty mapping means no inputs; `None` means no input snapshot was supplied.
The final layer and Studio input metadata are separate reads, not an atomic
snapshot. Package-level bindings are a separate category.

### Query behavior

Generated objects supply captured `.pql` expressions. All inline `${name}`
placeholders require explicit exact-string bindings, for generated and raw PQL:

```python
query = km.select(value="1 + ${days}")
result = query.execute(variables={"days": "7"}, limit=100)
```

Missing bindings raise `UnresolvedVariableError` even if captured metadata has a
default. Bindings are textual PQL fragments: they do not automatically quote
Python values, update View controls, or override server-managed KM variables.
Use `.eq()` when comparing an attribute with a Python value.

Execution uses `KnowledgeModelSaolaConnector` against live data. Captured
expressions stay fixed until regeneration and reload, while referenced cloud
dependencies resolve in the connected KM's selected lifecycle. No captured
layer is uploaded. To invoke a KPI's native parameter/filter semantics, use
its raw `KPI(...)` expression. Explicit textual bindings only affect submitted
expressions; they do not propagate into cloud dependencies.

## Review changes and check CI

```bash
uv run celofast km pull inventory --check
```

Check reads the cloud definition without changing files. Full captured metadata
still counts as drift, including categories with no generated navigation.
Reports label structure, symbols, types, definitions, metadata, and file changes.
Exit **0** means up to date/success, **1** means drift, and **2** means failure.

Pull regenerates the package; review the diff. Keep application code outside
the generated directory. Celofast refuses to replace unrelated files and restores
the previous package if replacement fails. Keep all four files together:
`__init__.py`, `capture.json`, `schema.json`, and `py.typed`.
Generated imports check the runtime version and capture integrity.

### Reload in a running Python process

Restart Python after pulling, or reload explicitly:

```python
import importlib
import generated.inventory as inventory_sdk

old_inventory = inventory_sdk.km
inventory_sdk = importlib.reload(inventory_sdk)
inventory = inventory_sdk.km
km = cf.km(inventory)
```

Existing definitions and queries retain their old capture. New objects use the
reloaded capture. Referenced cloud dependencies still resolve live. Generated
packages contain business metadata and PQL; use appropriate repository access.

## Native PQL tools

`km.build(query)` returns native `pycelonis.pql.PQL` for inspection. PyCelonis's
`PQLDebugger` and `PQLParser` live in their respective `pycelonis.pql` submodules
in the pinned dependency. They operate on Data Model expressions, not captured
KM context. Use KM execution to resolve KM references and inspect native error
chains; do not use a Data Model debugger as a substitute for KM resolution.
