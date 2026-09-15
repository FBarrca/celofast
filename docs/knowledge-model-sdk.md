# Capture a Knowledge Model as Python

Celofast generates a typed Python package containing your KM's definitions.
Import it to explore business objects, inspect their metadata, and use their
captured definitions in queries over live data.

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
celofast km pull inventory
```

You can also supply everything explicitly:

```bash
celofast km pull --space-id SPACE_ID --package-id PACKAGE_ID \
  --km inventory-km --mode draft --output generated/inventory
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
number = plant.attributes.number_formatted

number.id
number.description
number.column_type
number.pql
number.metadata  # Complete, deeply immutable source definition

cf = CeloFast(space_id="SPACE_ID", package_id="PACKAGE_ID", mode="draft")
result = cf.km(inventory).execute({
    "columns": {"Plant number": number},
}, limit=100)
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

Use generated attributes or KPIs for columns and ordering, and generated filters
for filtering:

```python
query = {
    "columns": {"Plant": number, "Value": inventory.kpis.inventory_value},
    "filters": [inventory.filters.active_inventory],
    "order_by": [{"pql": inventory.kpis.inventory_value, "ascending": False}],
}
native_pql = cf.km(inventory).build(query)
```

Binding checks tenant, Space, Package, KM key, lifecycle, and Data Model.
Generated roots and string keys share one native handle per KM; each generated
root is validated even when the handle is already cached.
Queries can combine generated attributes, KPIs, and filters with raw PQL strings.

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
celofast km pull inventory --check
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
verification for that reason. Use `handle.execute(query)` to resolve KM expressions through the native
connector and receive upstream resolution/export errors.
Do not send unresolved KM expressions to the Data Model debugger as a substitute.

Local `variables=` bindings remain an explicit text-template convenience; they
are not a PQL parser. The former captured-layer transport adapter was removed.
