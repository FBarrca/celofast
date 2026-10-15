# Celofast documentation

[Project overview](../README.md) · [Getting started](getting-started.md)

Celofast connects Python applications to Celonis business definitions and live
data. Knowledge Models become typed business objects you retrieve and traverse
in Python; View tables provide configured tabular inputs; results can be written
to augmentation tables.

## Guides

| Guide | Use it to |
| --- | --- |
| [Getting started](getting-started.md) | Install Celofast, authenticate, and run a first query. |
| [Knowledge Models](knowledge-model-sdk.md) | Load typed business objects, filter them, and follow relationships. |
| [Views](views.md) | Read a View's tables as DataFrames and its input fields' values. |
| [Augmentation tables](augmentation-tables.md) | Write predictions, scores, and other results back to Celonis. |

## Reference

| Page | Contents |
| --- | --- |
| [API reference](api-reference.md) | Every public call, argument, and command. |
| [Troubleshooting](troubleshooting.md) | Common errors and what to do about them. |
| [Augmentation architecture and limits](Augmentated_tables.md) | Storage, naming rules, and exact service limits. |
| [Augmentation platform reference](Augmentated_tables%20copy.md) | Table-backed attributes (TAA/V2, RAA/V1), Annotation Builder, and migration. |
| [Development](development.md) | Tests, code layout, and documentation maintenance. |

## The objects you work with

| Object | What it represents | Example |
| --- | --- | --- |
| `CeloFast` | A connection scoped to one Space, Package, and lifecycle | `cf = CeloFast("SPACE_ID", "PACKAGE_ID")` |
| Generated `inventory` | An offline registry of object types captured from one KM | `from generated.inventory import Plant, km as inventory` |
| `KnowledgeModelClient` | Retrieves objects from the connected KM | `client = cf.km(inventory)` |
| `Plant.fields` | The definition of an object type and its typed fields | `Plant.fields.country.eq("DE")` |
| `Plant` instance | One loaded, immutable business object | `plant = client.objects(Plant).get("P1")` |
| `ObjectCollection` / `ObjectPage` | A filterable set of objects / one fetched page | `client.objects(Plant).fetch_page()` |
| Relationship | A link to related objects, from a Data Model foreign key | `plant.links.material_master_plants.fetch_page()` |
| View table handle | A table component whose query comes from View configuration | `cf.view("operations-view")["Orders"]` |
| Augmentation table handle | A destination for rows in the resolved Data Model | `cf.augmentation_tables("inventory-km").table("PREDICTIONS")` |

The names in these examples are illustrative. Resource selectors use your exact
IDs or keys; generated class and field names derive from your KM.

## What is local and what is live?

```text
Cloud KM definitions -- celofast km pull --> generated object classes
                                                                     |
                                                            cf.km(inventory)
                                                                     |
                                   client.objects(Plant).fetch_page() --> live Plant objects
                                   plant.links.material_master_plants.fetch_page() --> live related objects
```

- Importing a generated package and inspecting definitions are offline.
- Creating `CeloFast` resolves the Space and Package. `cf.km(inventory)`
  resolves the KM and Data Model and validates the generated source.
- Building collections, predicates, and relationship accessors, and reading
  values from loaded objects, never fetch data. `get()`, `fetch_page()`,
  `next_page()`, and `ToOne.fetch()` do.
- `cf.view(key)` reads the View's definition. `table.rows()`, an input's
  `.value` and `.details()`, and a dropdown's `options()` each read live data.
- Augmentation mutations write to the underlying Data Model.

## Three distinctions that matter

**Definitions and loaded objects.** `Plant.fields.country` is a definition used
to filter; `plant.country` is a loaded value. Pulling captures definitions, not
data. Pull and restart Python when you want new definitions.

**Draft and published resources.** `mode="draft"` selects Studio resources;
`mode="published"` selects published Apps resources. The modes do not fall back
to each other. Use matching Space and Package IDs for the selected context.

**Input variables.** KM object reads and View table reads use the current
values of the KM's input variables on each read, and `view["Input"].value`
reads one. Reading an input does not filter KM objects by itself: use its value
in a predicate. See [Read an input field](views.md#4-read-an-input-field).

## Objects or View tables?

Use **KM objects** to retrieve identified business objects, filter them by
field values, and follow declared relationships. Use **View tables** when
Studio already defines the columns, KPIs, and filters of a tabular result you
need; they return DataFrames. The object SDK deliberately has no column
selection, aggregation, or PQL.
