# Celofast

**Typed Python objects for Celonis Knowledge Models.**

Celofast generates a Python package from a Celonis Knowledge Model (KM): one
class per business object, with typed fields and relationships your editor
autocompletes. Query them in plain Python, without writing PQL. Built for
Machine Learning Workbench (MLWB) apps, it also reads View tables and writes
results back to augmentation tables.

[Getting started](docs/getting-started.md) 

| Features| |
| --- | --- |
| Retrieve typed business objects and relationships | [Knowledge Models](docs/knowledge-model-sdk.md) |
| Read a View's tables and input fields | [Views](docs/views.md) |
| Store predictions, scores, or other app output | [Augmentation tables](docs/augmentation-tables.md) |

```python
from celofast import CeloFast
from generated.inventory import MaterialMasterPlant, Plant, km as inventory

client = CeloFast("SPACE_ID", "PACKAGE_ID").km(inventory)

stock = MaterialMasterPlant.fields
below_safety_stock_in_germany = (
    client.objects(MaterialMasterPlant)
    .where(
        stock.current_valuated_stock_quantity.lt(stock.safety_stock_quantity)
        & MaterialMasterPlant.relations.plant.has(Plant.fields.country.eq("DE"))
    )
    .fetch_page()
)
for material in below_safety_stock_in_germany:
    print(material.key, material.current_valuated_stock_quantity)
```

## Features

- **Generated from your KM.** Object types, keys, field types, and
  relationships come from the KM and its Data Model; no configuration needed.
- **Type-checked.** Fields, filters, and relationships are checked by your
  editor and type checker, and filter values are validated before any request.
- **One query per read.** Filters on related objects and aggregates such as
  `count()` or `sum()` run as a single PQL query in Celonis.
- **Live KM input variables.** Each read uses the KM's current input values.
- **Drift checks.** `celofast km pull --check` fails CI when the KM changes.
- **Views and output.** Read tables configured in Studio as DataFrames, and
  write predictions to augmentation tables.

## Install

Celofast requires Python 3.10 or newer:

```bash
uv add "celofast @ git+https://github.com/FBarrca/celofast.git"
```

## Quick start

**1. Configure authentication.** Put your OAuth client in `.env` (or the
environment), or pass an authenticated PyCelonis client to `CeloFast`
([details](docs/getting-started.md#2-configure-authentication)):

```dotenv
CELONIS_URL=https://YOUR_TENANT.celonis.cloud
OAUTH_CLIENT_ID=YOUR_CLIENT_ID
OAUTH_CLIENT_SECRET=YOUR_CLIENT_SECRET
OAUTH_SCOPES=YOUR_GRANTED_SCOPES
```

**2. Register your KM** in your application's `pyproject.toml`, using the KM's
exact key:

```toml
[tool.celofast.knowledge-models.inventory]
space-id = "SPACE_ID"
package-id = "PACKAGE_ID"
key = "inventory-km"
mode = "draft"
output = "generated/inventory"
```

**3. Generate the package:**

```bash
uv run celofast km pull inventory
```

Anything that can't be generated, such as a formula that fails in Celonis, is
skipped and listed at the top of the generated `objects.py`.

**4. Query:**

```python
from celofast import CeloFast
from generated.inventory import Plant, km as inventory

client = CeloFast("SPACE_ID", "PACKAGE_ID").km(inventory)

plant = client.objects(Plant).get("PLANT-1000")
print(plant.country)                                      # a loaded value

german = client.objects(Plant).where(Plant.fields.country.eq("DE")).fetch_page()
materials = plant.links.material_master_plants.fetch_page()   # related objects
```

Continue with the [Knowledge Model guide](docs/knowledge-model-sdk.md) for
filters, sorting, relationships, aggregates, and keeping the package in sync.

## Read a View table

For tabular inputs already configured in Studio, select a View by its exact key
and a table by its component ID or unique display name. View tables return
pandas DataFrames:

```python
cf = CeloFast("SPACE_ID", "PACKAGE_ID")

table = cf.view("operations-view")["Orders"]
orders = table.rows(limit=100)
```

See [Views](docs/views.md).

## Write application output

```python
tables = cf.augmentation_tables("orders-km")          # the KM locates its Data Model
output = tables.table("ML_ORDER_PREDICTIONS", key="ORDER_ID")
output.upsert(prediction_frame)                       # a pandas DataFrame
```

Writes change the underlying Data Model, which other KMs and Views may also
use. See [Augmentation tables](docs/augmentation-tables.md).

## Development

```bash
uv sync
uv run pytest
```

The tests run offline. Live tests against the repository's Inventory KM are
opt-in; see [Development](docs/development.md).
