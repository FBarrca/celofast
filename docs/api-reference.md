# API reference

[Documentation](index.md) · [KM guide](knowledge-model-sdk.md)

This is a compact reference to Celofast's public workflows. Examples use
`cf` for a `CeloFast` instance, `km` for a connected KM, and `query` for a builder
query. `/` in a signature marks a positional-only argument; `*` marks the
start of keyword-only arguments.

## Connection and selection

```python
from celofast import CeloFast, Query, QueryDefinition, get_celonis
```

| Call | Returns / behavior |
| --- | --- |
| `get_celonis(base_url=None)` | Cached OAuth-authenticated PyCelonis client. Uses environment/`.env` when no URL is supplied. |
| `CeloFast(space_id, package_id, *, mode="draft", client=None)` | A package-scoped connection. Mode is `draft` or `published`. |
| `cf.km("exact-key")` | Cached `KnowledgeModelHandle`. |
| `cf.km(generated_root)` | Connected copy with the root's precise generated type. Validates source and Data Model; leaves the original root unchanged. |
| `cf.view("exact-key", *, variables=None)` | A View handle, cached for that key and set of bindings. |

`cf.client`, `cf.space`, and `cf.package` expose the native resources.
`cf.mode` exposes the selected lifecycle. A KM exposes `native`, `data_model`,
and `augmentation_tables` for the resolved resources.

Source: [core.py](../celofast/core.py), [client.py](../celofast/client.py).

## Generated objects

| Object / member | Behavior |
| --- | --- |
| `km.records`, `km.kpis`, `km.filters`, etc. | Collections generated from the source definition. Available members depend on the capture. |
| `plant.attributes` | Canonical attribute collection with iteration and exact-ID lookup. |
| `plant.country` | Typed shortcut for an unambiguous attribute. |
| `collection["SourceID"]` | Exact-ID lookup; raises `KeyError` when absent or ambiguous. Static return type is the common object type. |
| `attribute.eq(value)` | Immutable equality predicate. `None` means `IS NULL`. |
| `attribute.asc()` / `.desc()` | Immutable sorting descriptor; also supported by KPIs. |
| `object.id`, `.description`, `.display_name`, `.column_type`, `.pql` | Captured metadata; optional fields can be `None`. |
| `object.metadata` | Complete, deeply immutable captured definition. |
| `inventory.input_variables` | Captured Studio input definitions by key; `None` for old captures without this snapshot. |
| `inventory.key`, `.mode`, `.capture` | KM identity, lifecycle, and underlying capture. |

Records represent definitions, not rows. They can be expanded by `select(record)`.
Other captured categories remain inspectable even when they have no executable
behavior. The available value types and equality encoding are explained in the
[KM guide](knowledge-model-sdk.md#attribute-equality-and-raw-filters).

Source: [objects.py](../celofast/sdk/objects.py),
[expressions.py](../celofast/expressions.py).

## Query builder

| Signature | Returns / behavior |
| --- | --- |
| `km.select(columns=None, /, **named_columns)` | `Query`. `columns` may be a record or a mapping; named columns are aliases. Empty selections and duplicate aliases fail. |
| `query.where(*filters)` | New `Query` with appended generated filters, equality predicates, or raw PQL filters. Conditions combine with AND. |
| `query.order_by(*expressions)` | New `Query` replacing the ordering. Plain expressions ascend; `.asc()`/`.desc()` choose direction. No arguments clears sorting. |
| `query.to_query()` | Fresh `QueryDefinition` dictionary retaining captured objects. |
| `query.build(*, variables=None)` | Native `pycelonis.pql.PQL`, with no data export. |
| `query.execute(*, variables=None, limit=None, offset=None, distinct=False)` | pandas DataFrame. `limit=None` requests all matching rows. |

Named columns accept raw PQL strings, generated attributes, or generated KPIs.
Whole-record selection uses exact attribute IDs as aliases and captured order
within `attributes`, `new_attributes`, and `augmented_attributes`, in that
collection order. Attributes need a non-empty ID and PQL expression.

Limits and offsets must be non-negative integers, excluding booleans.
`distinct` must be a boolean. `variables` must map non-empty string names to
exact string replacements. Queries and generated objects are immutable.

Source: [builder.py](../celofast/builder.py).

## Dictionary execution

| Signature | Returns |
| --- | --- |
| `km.build(query, *, variables=None)` | Native PQL. |
| `km.execute(query, *, variables=None, limit=None, offset=None, distinct=False)` | pandas DataFrame. |

`QueryDefinition` has required `columns` and optional `filters`/`order_by`.
`OrderByDefinition` has required `pql` and optional `ascending=True`.
See [Dictionary queries](dictionary-queries.md) for complete examples and
the validation differences from the builder.

Source: [query.py](../celofast/query.py),
[knowledge_model.py](../celofast/resources/knowledge_model.py).

## Views and controls

| Signature / member | Returns |
| --- | --- |
| `view.tables` | Tuple of table handles, root components followed by tab components. |
| `view.table(name_or_id)` | Table matched by exact ID or unique display name. |
| `table.to_query(*, inherit_filters_from=(), extra_filters=())` | Symbolic dictionary including configured, inherited, and extra filters. |
| `table.execute(*, inherit_filters_from=(), extra_filters=(), variables=None, limit=None, offset=None, distinct=False)` | pandas DataFrame. |
| `view.input_box(name_or_id)` | `InputBoxHandle`. |
| `view.dropdown(name_or_id)` / `.selector(name_or_id)` | `DropdownHandle` / `SelectorHandle`. |
| `view.date_picker(name_or_id)` / `.checkbox(name_or_id)` | `DatePickerHandle` / `CheckboxHandle`. |
| `control.get()` | Current decoded effective value. |
| `control.details()` | `InputVariableValue` for single-variable controls. |
| `dropdown.options(*, limit=None, offset=None)` | Tuple of `DropdownOption(value, label)` from a distinct query. |

All components expose `id`, `name`, `tab_name`, and `component`. Controls also
expose `settings`, `variable_keys`, and binding metadata. Range date pickers
use `get()` to return `DateRange(start, end)`; inspect `start_variable_key` and
`end_variable_key` instead of the single-variable interface.

Source: [view.py](../celofast/resources/view.py),
[view_input.py](../celofast/resources/view_input.py). More examples:
[Views and inputs](views-and-inputs.md).

## Augmentation tables

Let `tables = km.augmentation_tables` and `table = tables.table(...)`.

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

Exit codes: **0** means success/up to date; **1** means `--check` detected drift;
**2** means configuration, retrieval, generation, or installation failed.
Run `uv run celofast km pull --help` for the installed command's help.

Source: [cli.py](../celofast/cli.py). See
[reviewing generated changes](knowledge-model-sdk.md#review-changes-and-check-ci).

## Exceptions

Most Celofast exceptions are importable from `celofast`. `CeloFastError` is the
common base; `QueryValidationError` and `AugmentationValidationError` also
subclass `ValueError`. Generated import compatibility errors use
`celofast.sdk.loading.SDKCompatibilityError`, an `ImportError` subclass.

Native execution errors are not all converted to `CeloFastError`. The builder
wraps recognized query errors and preserves their cause chain; dictionary and
View execution retain native errors. Use the
[troubleshooting table](troubleshooting.md) to identify the failing layer.
