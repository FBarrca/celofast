# Celofast

**Work with Celonis Knowledge Models as typed Python objects. Write application
results through augmentation tables.**

Celofast is a Python library for the inputs and outputs of Machine Learning
Workbench (MLWB) apps. Retrieve business objects from Knowledge Models (KMs) and
follow their relationships, read configured View tables and controls, and write
results back through augmentation tables. Execution uses PyCelonis.

## Choose your starting point

| I want to… | Start here |
| --- | --- |
| Install Celofast and connect to a tenant | [Getting started](docs/getting-started.md) |
| Retrieve typed business objects and relationships | [Knowledge Model guide](docs/knowledge-model-sdk.md) |
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

## Work with Knowledge Model objects

After [configuring authentication](docs/getting-started.md#2-configure-authentication),
register your KM in your application's `pyproject.toml`, replacing the IDs and
key with your own:

```toml
[tool.celofast.knowledge-models.inventory]
space-id = "SPACE_ID"
package-id = "PACKAGE_ID"
key = "inventory-km"
mode = "draft"
output = "generated/inventory"

[tool.celofast.knowledge-models.inventory.mapping]
exclude = ["EL_CELONIS_DELIVERYLINE"]      # records that are not business objects

[tool.celofast.knowledge-models.inventory.mapping.objects.O_CELONIS_PLANT]
class = "Plant"
key = ["ID"]

[tool.celofast.knowledge-models.inventory.mapping.objects.O_CELONIS_PLANT.links.materials]
target = "O_CELONIS_MATERIALMASTERPLANT"
cardinality = "many"
on = { ID = "PLANT_ID" }
```

Every generated object type needs a verified key. `--check` lists each record,
key, type, and relationship that still needs a mapping or an explicit exclusion:

```bash
uv run celofast km pull inventory --check
uv run celofast km pull inventory
```

Then retrieve typed objects:

```python
from celofast import CeloFast
from generated.inventory import Plant, km as inventory

cf = CeloFast(space_id="SPACE_ID", package_id="PACKAGE_ID")
client = cf.km(inventory)

plant = client.objects(Plant).get("PLANT-1000")
print(plant.country)                               # str | None

page = (
    client.objects(Plant)
    .where(Plant.fields.country.eq("DE"))
    .fetch_page(page_size=100)
)
materials = plant.links.materials.fetch_page(page_size=50)
```

`Plant.fields.country` is a definition used for filtering; `plant.country` is a
loaded value. Objects are immutable, fully loaded snapshots: reading a value
never performs a request, while `get`, `fetch_page`, and relationship fetches
do. Keys are validated, values are decoded to their declared types, and a
failed request is an error, never an empty page. See the
[KM guide](docs/knowledge-model-sdk.md). Upgrading from the query API? Follow
the [0.5 migration guide](docs/migration-0.5.md).

## Reuse a View table

For tabular inputs already configured in Studio, select a View by its exact key
and a table by its component ID or unique display name. View tables return
pandas DataFrames:

```python
table = cf.view("operations-view").table("Orders")
orders = table.execute(limit=100)
```

The query includes the table's configured columns, filters, and sorting. See
[Views and inputs](docs/views-and-inputs.md) for discovery and control values.

## Write application output

For an existing augmentation table and a pandas DataFrame `prediction_frame`:

```python
tables = cf.augmentation_tables("orders-km")   # the KM locates its Data Model
output = tables.table("ML_ORDER_PREDICTIONS", key="ORDER_ID")
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
checks, and the opt-in live tests.

The repository's Inventory KM (configured in `pyproject.toml`, with its object
mapping in `inventory-objects.toml`) backs the opt-in live tests. Its generated
package is ignored by Git and must be pulled in each checkout.
