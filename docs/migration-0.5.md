# Migrating to 0.5: the Knowledge Model object SDK

[Documentation](index.md) · [KM guide](knowledge-model-sdk.md)

0.5 replaces the Knowledge Model query API with an object SDK. It is a
deliberate break: the old entry points have no compatibility aliases.

## What changed

| 0.4 | 0.5 |
| --- | --- |
| `km.select(...)`, `query.where/order_by/execute` | `client.objects(Plant).where(...).fetch_page()` |
| `km.execute(query_dict)`, `km.build(...)`, `query.to_query()` | Removed. |
| pandas DataFrame results | `Plant` objects in an `ObjectPage[Plant]` |
| `inventory.records.o_celonis_plant.country` (an `Attribute`) | `Plant.fields.country` (a `Field`) for filters; `plant.country` for values |
| `plant.country.eq("DE")` | `Plant.fields.country.eq("DE")` |
| `query.order_by(attribute.desc())` | `collection.order_by(Plant.fields.country.desc())` |
| Joins written as PQL or DataFrame merges | Declared links: `plant.links.materials`, `Plant.relations.materials.any(...)` |
| KPIs, KM filters, raw PQL filters | Not exposed by the object SDK |
| `cf.km("key")` | `cf.km(inventory)` only. Use `cf.augmentation_tables("key")` for output tables without a generated package. |
| `KnowledgeModelHandle` | `KnowledgeModelClient` (from `cf.km`); `view.km` is a `KnowledgeModelConnection` without query methods |
| Generated `__init__.py` with a record hierarchy, plus `capture.json` and `schema.json` | Plain Python: `definitions.py`, `objects.py`, `links.py`; `__init__.py` exports value classes and `km`. No data files. |
| Records without identity were queryable | Every record needs a verified key or an explicit exclusion |
| `inventory.input_variables`, `attribute.metadata`, `attribute.pql` | `inventory.variables` (names used by generated fields), `field.expression`, `field.display_name`, `field.description` |
| `km pull --check` reported any KM definition change | Reports a unified diff of the generated files; KM changes that don't affect generated types are not drift |
| Runtime API 5 | Runtime API 7 |

View tables are unchanged: `view.table(...).to_query()` and `.execute()` still
return dictionaries and DataFrames. They are a View feature, not part of the KM
SDK.

## Steps

1. Upgrade Celofast.
2. Register your KM (see
   [Register your KM](knowledge-model-sdk.md#1-register-your-km)). Object types,
   keys, types, and links are derived at pull; a `mapping` is only needed for
   [overrides](knowledge-model-sdk.md#overrides). Celonis `DATE` fields load as
   `datetime` (filters still accept a `date`); use `types = { X = "date" }` to
   keep a strict date.
3. Run `uv run celofast km pull inventory` and restart Python. Importing a
   package generated for the query API raises `SDKCompatibilityError` with a
   regeneration message.
4. Replace reads:

   ```python
   # 0.4
   km = cf.km(inventory)
   plant = inventory.records.o_celonis_plant
   frame = km.select(plant).where(plant.country.eq("DE")).execute(limit=100)

   # 0.5
   from generated.inventory import Plant, km as inventory
   client = cf.km(inventory)
   page = client.objects(Plant).where(Plant.fields.country.eq("DE")).fetch_page(page_size=100)
   ```

5. Replace joins you performed on DataFrames with declared `links`, and move
   `variables=` from each `execute()` call to `cf.km(inventory, variables=...)`.

## Workloads without an object equivalent

Aggregations across records, KPI columns, grouped results, and arbitrary PQL
are analytical workloads; the object SDK intentionally does not provide them.
Configure them as a View table and use `cf.view(...).table(...).execute()`, or
use PyCelonis directly through `client.native` and `client.data_model`.
