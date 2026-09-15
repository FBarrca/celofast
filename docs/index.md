# Celofast documentation

[Project overview](../README.md) · [Getting started](getting-started.md)

Celofast connects Python applications to Celonis business definitions and live
data. Its main workflow is: select the right input, fetch a pandas DataFrame,
process it in Python, and write results to an augmentation table when needed.

## Reading paths

| Task | Guide |
| --- | --- |
| First connection and first query | [Getting started](getting-started.md) |
| Typed records, attributes, KPIs, filters, and reusable queries | [Knowledge Models](knowledge-model-sdk.md) |
| Plain PQL, dictionary definitions, and serialization | [Dictionary queries](dictionary-queries.md) |
| Tables already configured in Studio and current control values | [Views and inputs](views-and-inputs.md) |
| Create, update, or remove application output | [Augmentation tables](augmentation-tables.md) |
| Augmentation architecture, naming rules, and exact service limits | [Architecture and limit notes](Augmentated_tables.md) |
| TAA/V2, legacy RAA/V1, Annotation Builder, and migration | [Detailed augmentation reference](Augmentated_tables%20copy.md) |
| Method signatures and return values | [API reference](api-reference.md) |
| Common failures and their next steps | [Troubleshooting](troubleshooting.md) |
| Upgrade existing KM applications to 0.4 | [Migration guide](migration-0.4.md) |
| Local tests, code layout, and documentation maintenance | [Development](development.md) |

## The objects you work with

| Object | What it represents | Example |
| --- | --- | --- |
| `CeloFast` | A connection scoped to one Space, Package, and lifecycle | `cf = CeloFast("SPACE_ID", "PACKAGE_ID")` |
| Generated `inventory` | A local, immutable snapshot of KM definitions | `from generated.inventory import km as inventory` |
| KM handle `km` | A cached connection for query execution | `km = cf.km(inventory)` |
| Record | A business-object definition, not one data row | `plant = inventory.records.o_celonis_plant` |
| Attribute or KPI | A captured expression and its metadata | `plant.country`, `inventory.kpis.inventory_value` |
| `Query` | An immutable selection, filters, and ordering | `km.select(plant).where(plant.country.eq("DE"))` |
| pandas DataFrame | The materialized query result | `query.execute()` |
| View table handle | A table component whose query comes from View configuration | `cf.view("operations-view").table("Orders")` |
| Augmentation table handle | A destination for rows in the resolved Data Model | `km.augmentation_tables.table("PREDICTIONS")` |

The names in these examples are illustrative. Resource selectors use your exact
IDs or keys; generated Python members derive from your captured KM IDs.

## What is local and what is live?

```text
Cloud KM definitions -- celofast km pull --> generated Python package
                                               |
                                      inspect and compose locally
                                               |
                                      cf.km(inventory)
                                               |
                                   query.execute() --> live DataFrame
```

- Importing a generated package and inspecting metadata are offline operations.
- Creating `CeloFast` resolves the Space and Package. Selecting a KM resolves
  its native handle and Data Model and validates a generated source.
- Once connected, composing a query, `build()`, and `to_query()` do not fetch
  query data. `execute()` does.
- View discovery loads View content. Its KM is resolved lazily when needed.
  Control `get()`/`details()` calls fetch current values; dropdown `options()`
  performs a separate data query.
- Augmentation mutations write to the underlying Data Model.

## Three distinctions that matter

**Captured definitions and live data.** Pulling captures expressions and
metadata, not rows. A captured expression can still reference a KPI whose
definition is resolved live. Pull and reload when you want new captured
definitions. See [KM execution semantics](knowledge-model-sdk.md#query-behavior).

**Draft and published resources.** `mode="draft"` selects Studio resources;
`mode="published"` selects published Apps resources. The modes do not fall back
to each other. Use matching Space and Package IDs for the selected context.

**Defaults and current user input.** Captured KM defaults, View template
bindings, and a user's current control values are separate sources. KM queries
require explicit `variables=` bindings; captured defaults are metadata only. Reading a
control does not automatically apply its value to every KM query. See
[View values and query bindings](views-and-inputs.md#values-and-query-bindings).

## Pick the right query path

Use **generated KM objects** for discoverability, metadata, autocomplete, and
reusable business queries. Use **dictionary queries** for existing PQL and
serializable configuration. Use **View tables** when Studio already defines
the columns and filters you need.

All three execute through the native Knowledge Model connector. A generated
query's `to_query()` bridges to the dictionary API while retaining its captured
objects and source information. Only dictionaries containing plain values such
as PQL strings can be serialized directly to JSON.
