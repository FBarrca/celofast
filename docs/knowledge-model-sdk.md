# Knowledge Models: typed objects and reusable queries

[Documentation](index.md) · [Getting started](getting-started.md) · [API reference](api-reference.md)

Celofast generates a typed Python package containing your KM's definitions.
Import it to explore business objects, inspect their metadata, and use their
captured definitions in queries over live data.

This guide assumes [authentication is configured](getting-started.md#2-configure-authentication).
Replace the example IDs and KM key with your own. Names such as
`o_celonis_plant`, `country`, and `active_inventory` are illustrative; the
generated members depend on your KM's definitions.

## In this guide

- [Configure and pull](#configure-and-pull)
- [Explore metadata and select records](#import-explore-and-query)
- [Compose and inspect queries](#compose-and-reuse-queries)
- [Apply attribute and raw filters](#attribute-equality-and-raw-filters)
- [Understand defaults and live execution](#native-execution)
- [Review drift and refresh a running process](#review-changes-and-check-ci)
- [Migrate older captures](#connections-and-compatibility)

For an existing PQL dictionary without generation, see
[Dictionary queries](dictionary-queries.md).

## Configure and pull

Add a model to your project's `pyproject.toml`:

```toml
[tool.celofast.knowledge-models.inventory]
space-id = "SPACE_ID"
package-id = "PACKAGE_ID"
key = "inventory-km"
mode = "draft"
output = "generated/inventory"
```

Configure the usual Celofast OAuth environment variables or `.env`, then run:

```bash
uv run celofast km pull inventory
```

You can also supply everything explicitly:

```bash
uv run celofast km pull --space-id SPACE_ID --package-id PACKAGE_ID --km inventory-km --mode draft --output generated/inventory
```

Configured output paths are relative to `pyproject.toml`. An explicit `--output`
is relative to your current directory. Use `--project path/to/pyproject.toml` to
select another project file. Draft and published are separate sources; Celofast
does not fall back between them.

## Import, explore, and query

Every generated package exports one object named `km`. Give it a useful local
name when importing:

```python
from celofast import CeloFast
from generated.inventory import km as inventory

plant = inventory.records.o_celonis_plant
number = plant.number_formatted

number.id
number.description
number.column_type
number.pql
number.metadata  # Complete, deeply immutable source definition

cf = CeloFast(space_id="SPACE_ID", package_id="PACKAGE_ID", mode="draft")
km = cf.km(inventory)
result = km.select({"Plant number": number}).execute(limit=100)
```

Member names derive from your KM IDs, so the exact available attributes depend
on your source. Your editor supplies autocomplete. Collections also support
iteration and exact-ID lookup:

```python
for attribute in plant.attributes:
    print(attribute.id, attribute.description)

number = plant.attributes["NumberFormatted"]
```

Generated properties retain precise types where authoritative metadata exists.
Exact-ID lookup returns the common object type because its key is a runtime
string. Unknown types use `Any`; unsupported categories remain discoverable as
generic objects. Capture diagnostics are recorded in `schema.json`.

These types describe captured declarations, not guaranteed pandas dtypes or
non-null result values. Inspect the DataFrame returned by execution when your
application depends on its concrete data representation.

Records expose direct shortcuts for unambiguous attributes from `attributes`,
`new_attributes`, and `augmented_attributes`. Shortcuts preserve the original
attribute type and metadata. Names that collide with record properties or
other attributes have no shortcut; use their original collection and exact ID.
For example, an attribute named `metadata` stays accessible through
`plant.attributes["metadata"]`, while `plant.metadata` describes the record.

### Select a complete record

```python
plant = km.records.o_celonis_plant
all_plants = km.select(plant)
active_plants = all_plants.where(km.filters.active_inventory)
plants = active_plants.where(plant.country.eq("DE")).execute(distinct=True)
```

The result is a pandas DataFrame. Whole-record selection includes every captured
attribute with a non-empty ID and non-empty PQL expression. It expands
`attributes`, then `new_attributes`, then `augmented_attributes`, preserving the
definition order within each collection. Other KM object types and attributes
without PQL are skipped. Column names are exact attribute IDs, such as
`NumberFormatted`, `Name`, and `Country`; conflicting IDs across collections
raise `QueryValidationError`. An empty record selection also raises this error.

Expansion retains the original generated attribute objects, including their
types, PQL, and metadata. For custom output names or a subset of fields, use
`km.select(plant_number=plant.number_formatted, plant_name=plant.name)`.

### Compose and reuse queries

Use generated attributes or KPIs for columns and ordering, and generated filters
for filtering:

```python
value = km.kpis.inventory_value
base = km.select(plant=km.records.o_celonis_plant.number_formatted, value=value)
active = base.where(km.filters.active_inventory)
largest = active.order_by(value.desc())

native_pql = largest.build()
result = largest.execute(limit=100)
query_dict = largest.to_query()
# The existing execution API accepts the same definition.
result = km.execute(query_dict, limit=100)
```

| Operation | Behavior |
| --- | --- |
| `km.select(plant)` | Select every queryable record attribute in captured order, with exact attribute IDs as column names. |
| `km.select(**columns)` | Select expressions with keyword output names. |
| `km.select({"Plant number": number})` | Select with arbitrary string output names. A mapping and keywords can be combined; duplicate names are rejected. |
| `query.where(*filters)` | Append generated filters, attribute predicates, or raw PQL filters, combined with AND. |
| `query.order_by(*expressions)` | Replace sorting. Plain expressions ascend; attributes and KPIs support `.asc()` and `.desc()`. No arguments clears sorting. |
| `query.build(variables=...)` | Compile native PQL without requesting query data. |
| `query.to_query()` | Return an independent dictionary retaining captured objects and their defaults. |
| `query.execute(...)` | Fetch a pandas DataFrame; accepts `variables`, `limit`, `offset`, and `distinct`. Omitting `limit` requests all matching rows. |

Composition is immutable: adding filters or changing sorting leaves the base
query unchanged. Columns and filters can combine generated objects with raw PQL
strings. Raw filters must be complete `FILTER ...;` statements. Repeated `where()`
calls append conditions; repeated `order_by()` calls replace the sorting.

For pagination, supply an ordering appropriate for your data and pass
`limit`/`offset` to execution. Each call queries live data, so concurrent data
changes can still move rows between pages. `distinct=True` requests distinct
result rows; it does not define a primary key for your business objects.

### Attribute equality and raw filters

```python
query = (
    km.select(plant)
    .where(km.filters.active_inventory)
    .where(plant.country.eq("DE"))
    .where('FILTER "Plant"."Active" = 1;')
)
plants = query.execute(limit=100, offset=0, distinct=True)
```

`attribute.eq(value)` returns an immutable predicate. It accepts strings, finite
numbers, booleans (encoded as 1/0), dates, and datetimes. `eq(None)` uses `IS NULL`.
The generated attribute's declared type is checked by static type checkers.
Strings use PQL escaping for quotes and backslashes; literal text is never
treated as a `${variable}` replacement. Datetimes use millisecond precision;
timezone-aware values are converted to UTC, and finer precision is rejected.
See Celonis's [string literals](https://help.celonis.com/pql46/en/string) and
[date constants](https://help.celonis.com/pql47/en/date) for the native syntax.

Attribute defaults and explicit `variables=` overrides are applied to the
attribute expression before the Python literal is added. Use repeated `where()`
calls to combine predicates with AND; Python `and`/`or` on a predicate raises
`QueryValidationError`. Other comparisons can be written as raw PQL filters.

`to_query()` retains captured objects, so its result is not necessarily JSON
serializable. It preserves the same variable-default behavior as direct dictionary
execution. `build()` and `execute()` use the existing native compilation path.

### Validation and errors

The builder raises `QueryValidationError` for empty selections, duplicate column
names, invalid filter objects, unsupported KM object types, and incompatible
captured sources. Limits and offsets must be non-negative integers, excluding
booleans; `distinct` must be a boolean.

Local PQL checks reject malformed filter statements, unclosed quotes or comments,
unbalanced delimiters, extra statements, and missing operands. `build()` also
checks the PQL after variable replacement. These are structural checks, not a
complete PQL parser: function signatures, KM references, and the remaining
grammar are resolved by Celonis during execution. The native KM connector has no
standalone validation service for these expressions.

During builder execution, native query-resolution errors and server errors
explicitly reporting syntax, parsing, or unknown-filter failures become
`QueryValidationError`, preserving the native error chain as the cause. Unrelated
export, permission, and connection failures retain their native exceptions.
The existing dictionary API retains its validation and native error behavior.

### Connections and compatibility

`cf.km(inventory)` returns a connected copy of the generated root, preserving
its precise type and autocomplete. The imported `inventory` remains offline
and unchanged. Connect before calling its query methods or accessing `native`,
`data_model`, or `augmentation_tables`.

Binding checks tenant, Space, Package, KM key, lifecycle, and Data Model on every
lookup. Connected copies share a cached native handle while keeping their own
captured definitions. Builder columns, filters, and sorting also reject generated
objects from another source or Data Model. String-key selection still returns
the cached handle, which supports both `select()` and dictionary queries.

Existing `cf.km(inventory).build(query_dict)` and `.execute(query_dict)` calls
continue to work. The returned generated object is now a connected copy rather
than the handle returned by `cf.km(inventory.key)`; callers must not rely on those
two results having the same object identity or concrete type.

Regenerate older packages with `celofast km pull` to get direct attribute
shortcuts and source attribute order. Older captures sorted record attributes
by ID; their original order cannot be recovered without pulling again. Attribute
reordering now changes the fingerprint and is reported by `--check`.
Older runtime-v1/v2 packages still import with this runtime; newly generated
runtime-v3 packages require the updated Celofast runtime. Review generation
diffs, including symbols that conflict with new API method names.

## Native execution

### Captured input defaults

Studio stores KM input-variable definitions separately from the final layer's
`variables` collection. Pull captures these by key, including type, scope, and
default value:

```python
inventory.input_variables["im_consideredfuturemonths"]["defaultValue"]
```

This mapping is deeply immutable and included in `capture.json`, integrity checks,
and `--check` drift reports. Regeneration and module reload expose updated defaults;
existing objects retain their old snapshot. Packages generated before this feature
return `None`; a newly captured KM without inputs returns an empty mapping.

These are declared defaults, not current View input values. Generated expressions
use captured string defaults to bind their inline placeholders; explicit
`variables=` entries take precedence. The final layer and Studio metadata are separate
reads of the selected lifecycle, not an atomic snapshot. Package-level bindings
are a different category and are not included in `input_variables`.

### Query behavior

Every query uses PyCelonis's `KnowledgeModelSaolaConnector`. Generated objects
supply their stored `.pql` expressions to native `pql.PQLColumn`, `pql.PQLFilter`,
and `pql.OrderByColumn` objects. No captured layer or custom query environment is
sent. Celonis handles parsing, dependency resolution, and execution errors.

Generated metadata stays fixed until regeneration. Execution uses live data and
resolves referenced KPIs, filters, and variables from the connected KM in the
selected draft/published mode. Capturing a definition does not freeze its
transitive dependencies. To call a KM KPI with its native filter/parameter
semantics, supply the appropriate `KPI(...)` expression as a raw PQL string.

Generated expressions bind inline variable placeholders using captured KM variable
values, then Studio input defaults, then explicit `variables=` overrides. Binding
uses exact string replacement, with no automatic quoting or type conversion.
Missing or null defaults require an explicit binding and fail locally if absent.
This binds only the submitted expression: references such as `KPI(...)` still
resolve through the live KM and do not receive these textual overrides.
Raw-string query templates retain their existing explicit-binding behavior.
Other generated categories remain inspectable and cannot be used as columns or
filters. Mutable View inputs are not automatically supplied to these queries.

Importing a generated package is offline. It does not load credentials, fetch
definitions, or import the PyCelonis query stack. The package contains business
metadata and PQL, so apply the repository permissions appropriate for that KM.

## Review changes and check CI

```bash
uv run celofast km pull inventory --check
```

Check retrieves the cloud definition and compares it with the generated package
without modifying files. Differences include object additions/removals, changed
fields, generated declarations, and local edits. Each line is labeled `structure`,
`symbols`, `type`, `definition`, `metadata`, or `files`. Symbol renames show both
names, including renames caused by a new naming collision. Documentation changes
also count as drift.

| Exit status | Meaning |
| --- | --- |
| 0 | Package matches, or pull completed successfully |
| 1 | Check found differences |
| 2 | Configuration, retrieval, generation, or installation failed |

Run pull to regenerate, then review the diff. Keep application code outside the
generated directory. Celofast refuses to replace unrelated files and restores
the previous package if replacement fails. Generated imports verify that their
declarations, captured content, and runtime API version agree.

The package contains `__init__.py`, `capture.json`, `schema.json`, and `py.typed`.
Include all four files when distributing or committing it.

### Reload in a running Python process

Pull updates the files on disk. Python keeps already imported modules cached;
importing the same package again does not adopt the new capture. Restart the
process or reload explicitly:

```python
import importlib
import generated.inventory as inventory_sdk

old_inventory = inventory_sdk.km
inventory_sdk = importlib.reload(inventory_sdk)
inventory = inventory_sdk.km
km = cf.km(inventory)
```

Existing objects such as `old_inventory` keep their captured definitions and
hierarchy, including objects removed by the new generation. The new `inventory`
reflects the latest pull. Referenced cloud dependencies still follow the native
execution semantics described above.

## Native PQL tools

Query construction and DataFrame execution use `import pycelonis.pql as pql`.
`handle.build(query)` returns a `pql.PQL`, whose columns, filters, and orderings
are native PyCelonis objects. Celofast validates the dictionary shape and captured
object categories; Celonis resolves PQL semantics and dependencies.

For diagnostics and filter parsing of **Data Model expressions**, use the
upstream tools directly with the handle's Data Model:

```python
import pycelonis.pql as pql
from pycelonis.pql.pql_debugger import PQLDebugger
from pycelonis.pql.pql_parser import PQLParser
from pycelonis.service.pql_language.service import PqlQueryType

handle = cf.km(inventory)
dm = handle.data_model
column = pql.PQLColumn(name="Number", query=number.pql)
errors = PQLDebugger.debug(
    dm.client, dm.id, column.query, PqlQueryType.DIMENSION
)
conditions = PQLParser.convert_filter_to_expressions(
    dm.client, dm.id, f"FILTER {column.query} IS NOT NULL;"
)
```

These tools call Celonis and require a connection. In pinned PyCelonis 2.15.1,
`PQLDebugger` and `PQLParser` live in their submodules, rather than being exported
as `pql.PQLDebugger` or `pql.PQLParser`. The language service does not validate KM
KPIs/variables in their captured context; the native KM connector skips query
verification for that reason. Use `handle.execute(query)` to resolve KM
expressions through the native connector and receive upstream
resolution/export errors.
Do not send unresolved KM expressions to the Data Model debugger as a substitute.

Local `variables=` bindings remain an explicit text-template convenience; they
are not a PQL parser.
