# Celofast

**Read Celonis data as pandas DataFrames. Write application results through
augmentation tables.**

Celofast is a Python library for the inputs and outputs of Machine Learning
Workbench (MLWB) apps. Use typed Knowledge Model (KM) objects to build reusable
queries, execute tables configured in Views, read View controls, and write
results back to the KM's Data Model. Execution uses PyCelonis.

## Choose your starting point

| I want to… | Start here |
| --- | --- |
| Install Celofast and connect to a tenant | [Getting started](docs/getting-started.md) |
| Query a whole record with autocomplete | [Knowledge Model guide](docs/knowledge-model-sdk.md) |
| Use existing PQL or a JSON query definition | [Dictionary queries](docs/dictionary-queries.md) |
| Read a configured table or input control | [Views and inputs](docs/views-and-inputs.md) |
| Store predictions, scores, or other app output | [Augmentation tables](docs/augmentation-tables.md) |
| Look up a method or diagnose an error | [API reference](docs/api-reference.md) · [Troubleshooting](docs/troubleshooting.md) |

See the [documentation index](docs/index.md) for the concepts and full reading
path. All documentation is Markdown in this repository.

## Install

Python 3.10 or newer is required. In your application's project:

```bash
uv add "celofast @ git+https://github.com/FBarrca/celofast.git"
```

Configure `CELONIS_URL`, `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, and
`OAUTH_SCOPES` in your environment or `.env`. You can also supply an authenticated
PyCelonis client. Follow [Getting started](docs/getting-started.md) for both paths.

## Query a Knowledge Model

Register your KM in your application's `pyproject.toml`, replacing the IDs and
key with your own:

```toml
[tool.celofast.knowledge-models.inventory]
space-id = "SPACE_ID"
package-id = "PACKAGE_ID"
key = "inventory-km"
mode = "draft"
output = "generated/inventory"
```

Pull its definitions into a typed Python package:

```bash
uv run celofast km pull inventory
```

The following example assumes the KM contains the illustrated plant record,
country attribute, and filter. Your generated names come from your KM's IDs.

```python
from celofast import CeloFast
from generated.inventory import km as inventory

cf = CeloFast(space_id="SPACE_ID", package_id="PACKAGE_ID")
km = cf.km(inventory)
plant = km.records.o_celonis_plant

plants = (
    km.select(plant)
    .where(km.filters.active_inventory)
    .where(plant.country.eq("DE"))
    .execute(distinct=True)
)
```

`plants` is a pandas DataFrame containing all queryable plant attributes for
active plants in Germany. Columns use captured attribute IDs and definition
order. With no `limit`, execution requests all matching rows; use
`.execute(limit=100)` to preview a result.

Select named columns, reuse a base query, or inspect its PQL:

```python
base = km.select(plant_number=plant.number_formatted, plant_name=plant.name)
german_plants = base.where(plant.country.eq("DE"))

native_pql = german_plants.build()
query_definition = german_plants.to_query()
```

The base query stays unchanged. Generated definitions stay fixed until you pull
and reload them; query data and referenced cloud dependencies remain live.
See the [KM guide](docs/knowledge-model-sdk.md) for sorting, defaults, drift
checks, source validation, and migration from older captures.

## Reuse a View table

With the `cf` connection above, select a View by its exact key and a table by
its component ID or unique display name:

```python
table = cf.view("operations-view").table("Orders")
orders = table.execute(limit=100)
```

The query includes the table's configured columns, filters, and sorting. See
[Views and inputs](docs/views-and-inputs.md) for discovery and control values.

## Write application output

For an existing augmentation table and a pandas DataFrame `prediction_frame`:

```python
output = km.augmentation_tables.table("ML_ORDER_PREDICTIONS", key="ORDER_ID")
output.upsert(prediction_frame)
```

Writes affect the underlying Data Model, including other consumers of that
table. See [Augmentation tables](docs/augmentation-tables.md) for a complete
DataFrame example, table creation, keys, batching, and failure behavior.

## Contribute

```bash
uv sync
uv run pytest
```

Read [Development](docs/development.md) for repository structure, documentation
checks, and the opt-in live tests. The sample `main.py` uses tenant-specific
resource constants; replace them before running it against your tenant.
