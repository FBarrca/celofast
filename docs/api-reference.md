# API reference

[Documentation](index.md) · [KM guide](knowledge-model-sdk.md)

This is a compact reference to Celofast's public workflows. Examples use
`cf` for a `CeloFast` instance, `inventory` for a generated object model,
`client` for a `KnowledgeModelClient`, and `Plant` for a generated value class.
`*` in a signature marks the start of keyword-only arguments.

## Connection and selection

```python
from celofast import CeloFast, KnowledgeModelClient, get_celonis
```

| Call | Returns / behavior |
| --- | --- |
| `get_celonis(base_url=None)` | Cached OAuth-authenticated PyCelonis client. Uses environment/`.env` when no URL is supplied. |
| `CeloFast(space_id, package_id, *, mode="draft", client=None)` | A package-scoped connection. Mode is `draft` or `published`. |
| `cf.km(inventory)` | `KnowledgeModelClient` for a generated object model. Validates Space, Package, lifecycle, KM, and Data Model. KM keys raise `TypeError`. Reads bind KM input variables with the KM's current values. |
| `cf.augmentation_tables("exact-km-key")` | Augmentation tables of the Data Model behind a KM; no generated package needed. |
| `cf.view("exact-key")` | A View handle, cached per key. |

`cf.client`, `cf.space`, and `cf.package` expose the native resources.
`cf.mode` exposes the selected lifecycle. `client.native`, `client.data_model`,
`client.augmentation_tables`, and `client.mode` expose the resolved KM resources.

Source: [core.py](../celofast/core.py), [client.py](../celofast/client.py).

## Generated packages

| Member | Behavior |
| --- | --- |
| `inventory` (`km` in the package) | `ObjectModel`: `iter()`, `len()`, `inventory["RECORD_ID"]` returns the class, `.source`, `.data_model_id`, `.variables` (the `${name}` KM inputs generated fields use, with their data types). |
| `Plant` | Frozen dataclass: `key` plus one plain-valued attribute per loaded field. |
| `Plant.fields` | `PlantDefinition`: one `Field` per loaded field; iteration in generated order; `["ATTRIBUTE_ID"]` exact lookup. |
| `Plant.fields.object_type`, `.key_fields`, `.metadata` | Captured record ID, key fields, and the record's `displayName` and `description`. |
| `Field.name`, `.id`, `.expression`, `.value_type`, `.nullable`, `.display_name`, `.description` | Generated name, attribute ID, captured expression, declared type, nullability (false for keys), and captured metadata. |
| `Field.eq(x)`, `.ne(x)` | `Predicate`. `x` is a value of the field's type or another field of the same object type; `None` is a value. |
| `Field.lt(x)`, `.lte(x)`, `.gt(x)`, `.gte(x)` | `Predicate`; false when either side is null. Not available for `bool`. |
| `Field.asc()`, `Field.desc()` | `Sort` for `order_by()`. |
| `Field.is_in(values)`, `.between(low, high)`, `.like(pattern)` | `Predicate` rendered as PQL `IN`, `BETWEEN` (inclusive), and `LIKE` (string fields). Nulls never match. |
| `a & b`, `a \| b`, `~a` | Combined `Predicate` of the same object type; `~` is an exact complement. |
| `Plant.relations.<to_one>.has(predicate=None)` | `Predicate`: the related object exists and matches. |
| `Plant.relations.<to_many>.any(predicate=None)` | `Predicate`: some related object exists and matches. |
| `Plant.relations.<to_many>.count(p=None)`, `.count_distinct(f, p=None)` | `Aggregate[int]` (`PU_COUNT`, `PU_COUNT_DISTINCT`); 0 without related values. |
| `Plant.relations.<to_many>.sum(f, p=None)`, `.avg(...)`, `.min(...)`, `.max(...)`, `.median(...)` | `Aggregate` (`PU_SUM`, `PU_AVG`, `PU_MIN`, `PU_MAX`, `PU_MEDIAN` with the upper middle value); NULL without related values. Compares (`eq` … `between`) and sorts like a field. Foreign-key links only. |
| `Plant.relations.<event_log>.contains(*a)`, `.excludes(*a)` | `Predicate` (`MATCH_ACTIVITIES` `NODE`, not `NODE_ANY`): the object's history has every / none of the activities. `excludes` also holds without events. |
| `Plant.relations.<event_log>.starts_with(*a)`, `.ends_with(*a)` | `Predicate` (`STARTING`, `ENDING`): the first / last activity is one of them. Not usable inside `has()`. |
| `plant.key` | Business key; a tuple for composite keys. |
| `plant.links.<name>` | `ObjectCollection[Target]` (to-many) or `ToOne[Target]` (to-one), derived from a Data Model foreign key. |
| `SalesOrderScheduleLineActivity` | `Event` (a frozen dataclass like `Plant`): one event of one lead object. Fields `case` (the lead's key), `event_id`, `activity` (the event type table, such as `e_celonis_PostGoodsIssue`), `timestamp`, and the log's other attributes. Key `(case, event_id)`. |
| `event.links.case` | `ToOne[Lead]`. The lead's `links.activities` (logs named `...Activities`) or `links.events` is an `EventLogRelation`. |
| `Plant.relations.link_targets`, `.link_sources` | `ObjectLinkRelation`, on a type the Data Model's Object Link graph connects (found at pull by test-running `LINK_SOURCE`): objects of the same type it links to / that link to it. Traversal, `any()`, and `count()` only (per-object `LINK_SOURCE`/`LINK_TARGET` counts). |

`Plant.relations.<name>` and `plant.links.<name>` are the same relationship;
its `.target` and `.on` describe it. Every relationship follows a Data Model
foreign key (or, for event logs, the join Celonis maintains between a log and
its lead object), so it supports traversal, predicates (`BIND`, `PU_COUNT`),
and aggregates. Every read, including nested relations, is one PQL query.

Activities are named by event type table (`e_celonis_PostGoodsIssue`) or type
name (`PostGoodsIssue`), checked against the Data Model's event types at pull;
an unknown name raises `ObjectValueError`.

Value types are `str`, `int`, `float`, `bool`, and `datetime`. Keys are
`str`, `int`, or `datetime`. Celonis `DATE` values are timestamps, so they are `datetime`
fields (`DateTimeField`); their filters also accept a `date`, meaning its
midnight.

Source: [definitions.py](../celofast/sdk/definitions.py),
[objects.py](../celofast/sdk/objects.py), [generate.py](../celofast/sdk/generate.py).

## Object retrieval

| Signature | Returns / behavior |
| --- | --- |
| `client.objects(Plant)` | `ObjectCollection[Plant]`; the class must come from the connected package. |
| `collection.where(*predicates)` | New collection; predicates combine with AND and must belong to the collection's type. |
| `collection.order_by(*sorts)` | New collection ordered by fields or relation aggregates of its type (`Sort`, or ascending when given plainly); the key breaks ties. |
| `collection.get(key)` | `Plant`; `ObjectNotFoundError` if absent. |
| `collection.fetch_page(page_size=100, *, offset=0)` | `ObjectPage[Plant]` in `order_by` order, then key order (events: `timestamp`, then key); `page_size` is 1–10,000. |
| `page.items`, `.offset`, `.page_size`, `.has_more` | Loaded objects and paging state; pages iterate and have a length. |
| `page.next_page()` | Following `ObjectPage`, or `None` after the last page. |
| `to_one.fetch()` | `Target \| None`. |

Every read loads all fields. `ObjectIdentityError` means a null key or
conflicting values for one key; `ObjectValueError` means a value does not match
its declared type. Native export errors propagate unchanged.

Source: [objects.py](../celofast/sdk/objects.py),
[hydration.py](../celofast/sdk/hydration.py),
[knowledge_model.py](../celofast/resources/knowledge_model.py).

## Views and controls

| Signature / member | Returns |
| --- | --- |
| `view.elements` | Tuple of supported input and table handles, root components followed by tab components. |
| `view[name_or_id]` | Element matched by exact ID or unique display name across input and table types. |
| `table.to_query(*, inherit_filters_from=(), extra_filters=())` | Symbolic dictionary including configured, inherited, and extra filters. |
| `table.rows(*, inherit_filters_from=(), extra_filters=(), limit=None, offset=None, distinct=False)` | Fresh pandas DataFrame; `${name}` input placeholders are bound with the inputs' current values. |
| `input.value` | Fresh decoded effective value for this input only. |
| `input.details()` | Current `InputVariableValue`, or `DateRangeDetails(start, end)` for a range date picker. |
| `dropdown.options(*, limit=None, offset=None)` | Tuple of `DropdownOption(value, label)` from a distinct query or the configured manual items. |

All components expose `id`, `name`, `tab_name`, and `component`. Controls also
expose `settings`, `variable_keys`, and binding metadata. Range date pickers
use `.value` to return `DateRange(start, end)`; inspect `start_variable_key` and
`end_variable_key` for the two bindings.

Source: [view.py](../celofast/resources/view.py),
[view_input.py](../celofast/resources/view_input.py). More examples:
[Views](views.md).

## Augmentation tables

Let `tables = cf.augmentation_tables("km-key")` (or `client.augmentation_tables`) and `table = tables.table(...)`.

| Signature | Returns / behavior |
| --- | --- |
| `tables.table(table_name, *, key=None)` | Cached lazy table handle. No remote existence check. |
| `tables.create(df, *, table_name, key, data_model_table_name, foreign_key_columns, batch_size=1000)` | Handle for the newly created and populated table. |
| `table.upsert(df, *, batch_size=1000)` | `None`; insert/update rows. |
| `table.remove(df, *, key=None, batch_size=1000)` | `None`; remove rows identified by a DataFrame key column. |
| `table.delete()` | `None`; permanently delete the entire remote table. |

The handle exposes `name`, `key`, `native`, and `data_model`. Batch size must be
an integer from 1 to 1,000. Writes are not transactional across batches and are
not isolated by KM lifecycle. See [Augmentation tables](augmentation-tables.md).

Source: [augmentation_table.py](../celofast/resources/augmentation_table.py).

## KM command line

```bash
uv run celofast km pull inventory
uv run celofast km pull inventory --check
uv run celofast km pull inventory --project path/to/pyproject.toml
uv run celofast km pull --space-id SPACE_ID --package-id PACKAGE_ID --km inventory-km --mode draft --output generated/inventory
```

| Argument | Meaning |
| --- | --- |
| `name` | Optional name under `[tool.celofast.knowledge-models]`. |
| `--project` | Explicit `pyproject.toml`; requires a configured name. Otherwise configuration is found from the working directory upward. |
| `--space-id`, `--package-id`, `--km` | Explicit source identifiers, overriding configured values. `--km` is the exact KM key. |
| `--mode` | `draft` or `published`; defaults to `draft` if not configured. |
| `--output` | Explicit output path, relative to the working directory. Configured output paths are relative to their `pyproject.toml`. |
| `--check` | Read cloud definitions and report drift without changing files. |

Pull reads Data Model tables, primary keys, column types, and foreign keys, and
test-runs calculated attributes against a sample of rows. Progress goes to
stderr: a progress bar in a terminal, otherwise one line per step.

Exit codes: **0** means success/up to date; **1** means `--check` detected drift;
**2** means configuration, retrieval, generation, or installation failed.
Run `uv run celofast km pull --help` for the installed command's help.

Source: [cli.py](../celofast/cli.py). See
[reviewing generated changes](knowledge-model-sdk.md#9-keep-the-package-up-to-date).

## Exceptions

Most Celofast exceptions are importable from `celofast`. `CeloFastError` is the
common base; `QueryValidationError`, `AugmentationValidationError`, and
`ObjectValueError` also subclass `ValueError`.
`ObjectNotFoundError` subclasses `ResourceNotFoundError`; `ObjectIdentityError`
reports null keys and conflicting values. Generated import compatibility errors use
`celofast.sdk.loading.SDKCompatibilityError`, an `ImportError` subclass.

Object reads and View execution preserve native exception types and cause
chains. Celofast validates overrides, predicates, identity, and values;
Celonis validates PQL syntax and semantics. Use the
[troubleshooting table](troubleshooting.md) to identify the failing layer.
