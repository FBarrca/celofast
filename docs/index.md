# Celofast documentation

[Project overview](../README.md) · [Getting started](getting-started.md)

Celofast connects Python applications to Celonis business definitions and live
data. Knowledge Models become typed business objects you retrieve and traverse
in Python; View tables provide configured tabular inputs; results can be written
to augmentation tables.

## Reading paths

| Task | Guide |
| --- | --- |
| First connection and first objects | [Getting started](getting-started.md) |
| Typed business objects, keys, filters, and relationships | [Knowledge Models](knowledge-model-sdk.md) |
| Tables already configured in Studio and current control values | [Views and inputs](views-and-inputs.md) |
| Query dictionaries exported from View tables | [View query dictionaries](dictionary-queries.md) |
| Create, update, or remove application output | [Augmentation tables](augmentation-tables.md) |
| Augmentation architecture, naming rules, and exact service limits | [Architecture and limit notes](Augmentated_tables.md) |
| TAA/V2, legacy RAA/V1, Annotation Builder, and migration | [Detailed augmentation reference](Augmentated_tables%20copy.md) |
| Method signatures and return values | [API reference](api-reference.md) |
| Common failures and their next steps | [Troubleshooting](troubleshooting.md) |
| Upgrade KM applications from the 0.4 query API | [Migration guide](migration-0.5.md) |
| Local tests, code layout, and documentation maintenance | [Development](development.md) |

## The objects you work with

| Object | What it represents | Example |
| --- | --- | --- |
| `CeloFast` | A connection scoped to one Space, Package, and lifecycle | `cf = CeloFast("SPACE_ID", "PACKAGE_ID")` |
| Generated `inventory` | An offline registry of object types captured from one KM | `from generated.inventory import Plant, km as inventory` |
| `KnowledgeModelClient` | Retrieves objects from the connected KM | `client = cf.km(inventory)` |
| `Plant.fields` | The definition of an object type and its typed fields | `Plant.fields.country.eq("DE")` |
| `Plant` instance | One loaded, immutable business object | `plant = client.objects(Plant).get("P1")` |
| `ObjectCollection` / `ObjectPage` | A filterable set of objects / one fetched page | `client.objects(Plant).fetch_page()` |
| Relationship | A declared link to related objects | `plant.links.materials.fetch_page()` |
| View table handle | A table component whose query comes from View configuration | `cf.view("operations-view").table("Orders")` |
| Augmentation table handle | A destination for rows in the resolved Data Model | `cf.augmentation_tables("inventory-km").table("PREDICTIONS")` |

The names in these examples are illustrative. Resource selectors use your exact
IDs or keys; generated class and field names derive from your KM and mapping.

## What is local and what is live?

```text
Cloud KM definitions + object mapping -- celofast km pull --> generated object classes
                                                                     |
                                                            cf.km(inventory)
                                                                     |
                                   client.objects(Plant).fetch_page() --> live Plant objects
                                   plant.links.materials.fetch_page() --> live related objects
```

- Importing a generated package and inspecting definitions are offline.
- Creating `CeloFast` resolves the Space and Package. `cf.km(inventory)`
  resolves the KM and Data Model and validates the generated source.
- Building collections, predicates, and relationship accessors, and reading
  values from loaded objects, never fetch data. `get()`, `fetch_page()`,
  `next_page()`, and `ToOne.fetch()` do.
- View discovery loads View content. Its KM is resolved lazily when needed.
  Control `get()`/`details()` calls fetch current values; dropdown `options()`
  performs a separate data query.
- Augmentation mutations write to the underlying Data Model.

## Three distinctions that matter

**Definitions and loaded objects.** `Plant.fields.country` is a definition used
to filter; `plant.country` is a loaded value. Pulling captures definitions, not
data. Pull and restart Python when you want new definitions.

**Draft and published resources.** `mode="draft"` selects Studio resources;
`mode="published"` selects published Apps resources. The modes do not fall back
to each other. Use matching Space and Package IDs for the selected context.

**Defaults and current user input.** KM input variables, View template
bindings, and a user's current control values are separate sources. Object
reads bind KM input variables with the KM's current values on each read.
Reading a control does not automatically filter
objects. See [View values and object filters](views-and-inputs.md#values-and-object-filters).

## Objects or View tables?

Use **KM objects** to retrieve identified business objects, filter them by
field values, and follow declared relationships. Use **View tables** when
Studio already defines the columns, KPIs, and filters of a tabular result you
need; they return DataFrames. The object SDK deliberately has no column
selection, aggregation, or PQL.
