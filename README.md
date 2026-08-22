# celofast

Celofast is a compact, PyCelonis-native API for reusable Knowledge Model
queries and table queries configured in Studio Views.

It keeps query definitions as ordinary serializable dictionaries while using
PyCelonis `ViewContent`, `Table`, `PQL`, and `KnowledgeModelSaolaConnector`
objects for the Celonis-specific semantics.

## Configuration

Copy `.env.example` to `.env` and configure:

- `CELONIS_URL`
- `OAUTH_CLIENT_ID`
- `OAUTH_CLIENT_SECRET`
- `OAUTH_SCOPES`, normally including `studio integration.data-pools`

Alternatively, inject an existing PyCelonis client into `CeloFast`.

## Query a Knowledge Model

Configure the Space and Package once, then select Knowledge Models by their
exact Studio keys:

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

Filters are native PQL filter statements. KPI expressions, KM record
attributes, named filters such as `FILTER @active_suppliers;`, and KM variables
are resolved by Celonis through `KnowledgeModelSaolaConnector`.

Use `km.build(query)` to inspect the native SaolaPy `PQL` without executing it.
With no `limit`, all matching rows are requested.

## Export and execute a View table

Views are selected by exact Studio key. Tables can be selected by unique
display name or stable component ID:

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

## Native escape hatches

The wrappers expose the resolved SDK resources without repeating lookups:

```python
km = cf.km("orders-km")
native_km = km.native
data_model = km.data_model

view = cf.view("operations-view")
native_view = view.native
native_table_component = view.table("Orders").component
```

Celofast 0.2 targets Studio draft resources. Published Apps resources are not part of this release.

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
