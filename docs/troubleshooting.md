# Troubleshooting

[Documentation](index.md) · [API reference](api-reference.md)

Start with the layer named by the exception: authentication, resource selection,
generated definitions, query construction, execution, or output writes.

## Connection and resource selection

| Symptom | Check / next step |
| --- | --- |
| `RuntimeError` naming a missing OAuth value | Set every required value in [Getting started](getting-started.md#2-configure-authentication). Check the working directory used to find `.env`. |
| Native authentication or permission failure | Verify the client, granted scopes, and access to the exact Space/Package and Data Model. Supplying IDs does not grant access. |
| `ResourceNotFoundError` for a KM or View | Use its exact key, not its display name. Confirm the selected Package and lifecycle. |
| `ResourceAmbiguityError` | More than one native resource matched the key. Resolve the duplicate source definitions. |
| `ResourceResolutionError` mentioning a Data Model | Confirm the KM has a final Data Model ID and the client can access that model through a Data Pool. |
| Published resources are missing | Pass the published Space/Package IDs and `mode="published"`. There is no draft fallback. |

`cf.client`, `cf.space`, `cf.package`, `cf.mode`, `km.native`, and `km.data_model`
help identify the actual resources selected by your application.

## Generated definitions and imports

| Symptom | Check / next step |
| --- | --- |
| `ModuleNotFoundError` for `generated.inventory` | Run the configured pull and make its output importable from the application's working directory or package. |
| `SDKCompatibilityError` on import | Include all four generated files and use a compatible Celofast runtime. Regenerate rather than editing generated files. |
| Missing `plant.country` field | Iterate over `plant` and use `plant["ExactID"]`. Colliding field names have suffixes listed in `schema.json`; ambiguous IDs need `get_attribute(..., collection="attributes")`. Regenerate older packages. |
| Unknown collection member | Generated names come from your captured IDs. Use iteration/autocomplete or `collection["ExactID"]`; absent IDs raise `KeyError`. |
| Missing `inventory.select` or `km.records` | Read fields from the generated `inventory`; call query methods on `km = cf.km(inventory)`. See the [0.4 migration guide](migration-0.4.md). |
| `QueryValidationError` about source or Data Model | Connect to the matching tenant, Space, Package, lifecycle, and Data Model. Do not mix expressions from other sources. |
| Cloud edits are missing after pull | Restart Python or reload the generated module, then reconnect the new root. Existing objects retain their previous capture. |
| Whole-record columns appear ID-sorted | Pull again: older captures sorted attribute lists by ID. New captures preserve definition order. |
| Pull refuses the output directory | Keep application code outside the managed directory. Use a separate output for a different KM source. |

See [KM compatibility](knowledge-model-sdk.md#connections-and-compatibility)
and [reload instructions](knowledge-model-sdk.md#reload-in-a-running-python-process).

## Query construction and execution

| Symptom | Check / next step |
| --- | --- |
| Empty selection / no queryable attributes | Select at least one expression. Whole-record attributes need non-empty IDs and PQL. |
| Duplicate output name or record attribute ID | Use explicit aliases for the intended fields. |
| `UnresolvedVariableError` | Supply the missing exact string binding. Both raw and generated expressions require explicit bindings; captured defaults are metadata only. |
| `eq()` rejects a value | Use a supported scalar/date or `None`. Numbers must be finite; datetimes need millisecond precision. |
| Python `and`/`or` on predicates raises an error | Chain `.where(...)` calls, or pass several filters to one call, to combine them with AND. |
| Invalid raw filter | Supply a complete `FILTER condition;` statement. Check quotes, comments, parentheses, and operands. |
| Invalid pagination | Use non-negative integers for `limit` and `offset`, and a boolean for `distinct`. Booleans are not valid limits. |
| `QueryValidationError` before export | Check the query shape, captured source, bindings, and execution options. PQL grammar is validated by Celonis during execution. |
| Native execution/export error | Inspect the exception chain for source resolution, syntax, permission, or service failures. Builder, dictionary, and View execution preserve native errors. |

Inspect the exact PQL after binding without exporting data:

```python
native_pql = query.build()
for column in native_pql.columns:
    print(column.name, column.query)
for filter_ in native_pql.filters:
    print(filter_.query)
```

Pass the same `variables=` mapping to `build()` that you use for execution.
Printed PQL and metadata can contain business information; review the content
before sharing a diagnostic.

A Data Model PQL debugger does not validate unresolved KM expressions in their
KM context. See [native PQL tools](knowledge-model-sdk.md#native-pql-tools).

## Views and controls

| Symptom | Check / next step |
| --- | --- |
| Missing or ambiguous table/control | Iterate `view.tables` or `view.controls` and select the exact ID. Names are case-sensitive and must be unique. |
| `ComponentVariableError` | Check `onChange.update.variables` in the native component configuration and the KM input definitions. |
| A range picker rejects `variable_key` or `details()` | Use `get()` for `DateRange`, plus `start_variable_key` and `end_variable_key`. |
| Dropdown selection differs from `options()` | `get()` reads current selection; `options()` queries the configured data-source attribute. |
| A control value is not affecting a KM query | Explicitly use it in a predicate or binding. Control reads do not automatically alter other queries. |
| Missing/invalid value response | Check the View's associated KM and Package Manager response. Dates must be ISO dates; checkboxes must decode as booleans. |

## Augmentation writes

| Symptom | Check / next step |
| --- | --- |
| A lazy reference succeeds but its first operation fails | `table()` does not verify existence. Create the table explicitly or correct its name. |
| `AugmentationValidationError` | Check DataFrame columns, keys, foreign-key pairs, and `batch_size` in [Augmentation tables](augmentation-tables.md). |
| A draft write affects another consumer | Writes target the shared Data Model table; draft/published mode does not isolate them. |
| A later batch fails | Earlier batches and the schema may already exist. Inspect remote state before retrying; there is no automatic rollback. |
| A new column does not appear after upsert | Upsert does not extend the existing schema. Plan schema changes through the appropriate native/platform workflow. |
| Native API, quota, or permission error | Check the tenant's augmentation API availability, Data Model write access, and service-level limits. |
