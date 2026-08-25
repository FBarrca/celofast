# celofast

Celofast aims to provide an easy way for us to define the input and output
(I/O) of Machine Learning Workbench (MLWB) apps. It makes reusable Knowledge
Model queries and table queries configured in Studio Views compact and
straightforward to consume, and writes operational results through Data Model
augmentation tables.

It keeps query definitions as ordinary serializable dictionaries while using
PyCelonis `ViewContent`, `Table`, `PQL`, and `KnowledgeModelSaolaConnector`
objects for the Celonis-specific semantics.

> [!NOTE]
>  The Current Augmentation Tables API in Pycelonis is very limited, go to [Augmentation tables](docs/Augmentated_tables.md) to see its what it is, its limitations, and how it differs from Augmented Attributes.

## Installation

Install the package from the `FbarrCa` GitHub repository with
[`uv`](https://docs.astral.sh/uv/):

```bash
uv add "celofast @ git+https://github.com/FbarrCa/celofast.git"
```

Alternatively, install it with `pip`:

```bash
pip install "celofast @ git+https://github.com/FbarrCa/celofast.git"
```

The package requires Python 3.10 or later. Its PyCelonis dependencies are
hosted on the Celonis package repository and are referenced by verified direct
artifact URLs in the package metadata, so `pip` does not need a custom index
configuration. Your environment must still be able to access that repository
and provide credentials if your organization requires them.

## Configuration

Copy `.env.example` to `.env` and configure:

- `CELONIS_URL`
- `OAUTH_CLIENT_ID`
- `OAUTH_CLIENT_SECRET`
- `OAUTH_SCOPES`, normally including `studio integration.data-pools`

Alternatively, inject an existing PyCelonis client into `CeloFast`.
### API Key
THe OAuth key has to have at least the following scopes:
- integration.data-pools:read
- integration.data-pools
- studio
- studio.packages:read
In addition the following permissions should be given:
- Studio -> Grant all **for the specific Space**
- Data integration -> Grant all **for the specific DM**

> ![DANGER] 
> For the augmentation feature to work the following feature flag has to be activated:
> `integration.enable-external-augmentation-api`

## Query a Knowledge Model

Configure the Space and Package once, then select Knowledge Models by their
exact keys. Draft mode uses Studio resources by default:

```python
from celofast import CeloFast, QueryDefinition

cf = CeloFast(
    space_id="SPACE_ID",
    package_id="PACKAGE_ID",
)

query: QueryDefinition = {
    "columns": {
        "Supplier": '"O_CELONIS_VENDOR"."SupplierNumberNameConcat"',
        "Purchase Order Value": (
            'KPI("IM_PurchaseDocumentLine_PurchaseDocumentLineValue")'
        ),
    },
    "filters": [
        'FILTER "O_CELONIS_VENDOR"."Country" = \'DE\';',
        "FILTER @active_suppliers;",
    ],
    "order_by": [
        {
            "pql": 'KPI("IM_PurchaseDocumentLine_PurchaseDocumentLineValue")',
            "ascending": False,
        }
    ],
}

result = cf.km("orders-km").execute(query, limit=100)
```

For a published Apps package, select the published context explicitly:

```python
published = CeloFast(
    space_id="PUBLISHED_SPACE_ID",
    package_id="PUBLISHED_PACKAGE_ID",
    mode="published",
)

result = published.km("orders-km").execute(query, limit=100)
```

Filters are native PQL filter statements. KPI expressions, KM record
attributes, named filters such as `FILTER @active_suppliers;`, and KM variables
are resolved by Celonis through `KnowledgeModelSaolaConnector`.

Use `km.build(query)` to inspect the native SaolaPy `PQL` without executing it.
With no `limit`, all matching rows are requested.

## Export and execute a View table

Views are selected by exact key in either context. Tables can be selected by
unique display name or stable component ID:

```python
view = cf.view("operations-view")
table = view.table("Supplier Performance")

query = table.to_query()
result = table.execute(limit=100)

same_table = view.table("table-c63f521e-a290-46be-845f-f101256fc1fd")
```

`to_query()` uses PyCelonis `Table.get_query()` and preserves all configured
data-source columns, component filters, referenced KM filters, and sorting.
Tables are discovered both at the View root and inside tabs.

Filters can be composed without changing the View:

```python
events = view.table("Events").execute(
    inherit_filters_from=("Orders",),
    extra_filters=('FILTER "Events"."VALID" = 1;',),
)
```

## Template variables

`${name}` placeholders are left intact by `to_query()` and replaced immediately
before execution. Values are exact strings, not automatic Python-to-PQL
conversions:

```python
view = cf.view("operations-view", variables={"days": "30"})

# Execution-level values override View-level values and configured defaults.
result = view.table("Events").execute(variables={"days": "7"})
```

These bindings are client-side View/query template replacements. They do not
override server-managed Knowledge Model variables.

## Write MLWB output to augmentation tables

The Knowledge Model handle exposes augmentation-table operations for its
resolved Data Model. The KM provides the convenient package-level route to the
correct Data Model; the augmentation table itself remains a Data Model
resource:

```python
km = cf.km("orders-km")

predictions = km.augmentation_tables.table(
    "ML_ORDER_PREDICTIONS",
    key="ORDER_ID",
)
predictions.upsert(prediction_frame)
```

`table()` returns a lazy native-backed reference. As with PyCelonis
`DataModel.get_augmentation_table()`, it does not verify that the table exists;
a missing-table error is raised by the first native operation.

Creating a table is intentionally explicit because PyCelonis infers its schema
from the initial DataFrame:

```python
predictions = km.augmentation_tables.create(
    prediction_frame,
    table_name="ML_ORDER_PREDICTIONS",
    key="ORDER_ID",
    data_model_table_name="O_CELONIS_ORDER",
    foreign_key_columns=[("ORDER_ID", "ORDER_ID")],
)

predictions.upsert(new_predictions)
predictions.remove(obsolete_order_ids)
```

Create, upsert, and remove operations are automatically split into requests of
at most 1,000 rows. Batches are not transactional: if a later request fails,
earlier batches may already have been applied. Native PyCelonis and API errors
are preserved.

Augmentation writes are independent of CeloFast's `draft` or `published` mode.
Both modes resolve a KM to its underlying Data Model, and a write can affect
every KM or View consuming that augmentation table. See
[Augmentation tables](docs/Augmentated_tables.md) for the intended use cases
and platform limits.

## Native escape hatches

The wrappers expose the resolved SDK resources without repeating lookups:

```python
km = cf.km("orders-km")
native_km = km.native
data_model = km.data_model
native_augmentation_table = (
    km.augmentation_tables.table("ML_ORDER_PREDICTIONS").native
)

view = cf.view("operations-view")
native_view = view.native
native_table_component = view.table("Orders").component
```

Celofast 0.2.1 supports both Studio draft resources and published Apps
resources. Select the lifecycle context with ``mode="draft"`` or
``mode="published"``; there is no automatic fallback between them.

## Run the example

`main.py` contains a hardcoded example for the Inventory Management package,
covering both a direct KM query and a View table query:

```bash
uv run python main.py
```

Only the tenant credentials in `.env` are required.

## Tests

```bash
uv sync
uv run pytest
```
