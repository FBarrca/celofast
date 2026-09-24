# Troubleshooting

[Documentation](index.md) · [API reference](api-reference.md)

Start with the layer named by the exception: authentication, resource selection,
generated packages, object retrieval, Views, or output writes.

## Connection and resource selection

| Symptom | Check / next step |
| --- | --- |
| `RuntimeError` naming a missing OAuth value | Set every required value in [Getting started](getting-started.md#2-configure-authentication). Check the working directory used to find `.env`. |
| Native authentication or permission failure | Verify the client, granted scopes, and access to the exact Space/Package and Data Model. Supplying IDs does not grant access. |
| `ResourceNotFoundError` for a KM or View | Use its exact key, not its display name. Confirm the selected Package and lifecycle. |
| `ResourceAmbiguityError` | More than one native resource matched the key. Resolve the duplicate source definitions. |
| `ResourceResolutionError` mentioning a Data Model | Confirm the KM has a final Data Model ID and the client can access that model through a Data Pool. |
| Published resources are missing | Pass the published Space/Package IDs and `mode="published"`. There is no draft fallback. |

`cf.client`, `cf.space`, `cf.package`, `cf.mode`, `client.native`, and
`client.data_model` help identify the actual resources selected by your application.

## Generating object packages

| Symptom | Check / next step |
| --- | --- |
| `ObjectMappingError` during pull | An override is invalid: it names an unknown record or attribute, sets an unusable key, repeats a class name, or declares a broken link. Fix the listed [overrides](knowledge-model-sdk.md#overrides). |
| A record or field you need is missing | Look under `# Not generated:` at the top of the generated `definitions.py` for the reason. A record without a primary key needs `key = ["ID"]`; an untyped attribute needs `types`; an attribute with `${...}` inputs needs `include-fields`; an attribute that fails in Celonis must be fixed in the KM, then pulled again. |
| Pull refuses the output directory | Keep application code outside the managed directory. Use a separate output for a different KM source. |
| `ModuleNotFoundError` for `generated.inventory` | Run the configured pull and make its output importable from the application's working directory or package. |
| `SDKCompatibilityError` on import | The package was generated for another runtime (for example the 0.4 query API). Rerun `celofast km pull` and restart Python; keep all generated files together. |
| A field has an unexpected name | Reserved or colliding names get suffixes, such as `key_attribute`; `definitions.py` lists each field with its attribute ID. Look fields up by attribute ID with `Plant.fields["ID"]`. |
| Missing `km.select`, `km.execute`, or `inventory.records` | The query API was removed. See the [0.5 migration guide](migration-0.5.md). |
| `TypeError` from `cf.km("key")` | Pass the generated model: `cf.km(inventory)`. Use `cf.augmentation_tables("key")` for output tables. |
| `QueryValidationError` about source or Data Model | Connect to the matching tenant, Space, Package, lifecycle, and Data Model. |
| Cloud edits are missing after pull | Restart Python so every generated module reloads with the new capture. |

## Retrieving objects

| Symptom | Check / next step |
| --- | --- |
| `ObjectNotFoundError` | No object has that key. Composite keys are tuples in key-field order (`Plant.fields.key_fields`). |
| `ObjectIdentityError` | The key is null, or one key produced different values. The key is not unique for that record, or a field's expression joins to several rows; choose another key or exclude the field. |
| `ObjectValueError` | A retrieved value does not match the declared type, or a filter value has the wrong type. Correct `types` in the mapping, or pass a value of the field's type. |
| `UnresolvedVariableError` | A loaded field uses a `${name}` KM input variable. Pass `variables=` to `cf.km(...)`, or exclude the field. |
| `QueryValidationError` from `where()` | Use predicates from the collection's own class, such as `Plant.fields.country.eq(...)`. Raw PQL is not accepted. |
| Native export error, such as an error in another record's calculated attribute | A loaded field depends on a definition that fails in Celonis. Inspect the exception chain and exclude the affected fields until the KM is fixed. |
| Python `and`/`or` on predicates raises an error | Pass several predicates to `where()` or chain calls; they combine with AND. |
| `Plant.relations` has no attribute for a declared link | The link matches no Data Model foreign key, and is not a single-column to-one link that `LOOKUP` can join. `definitions.py` lists it under "Not generated". Use `plant.links.<name>` for traversal, or align the mapping with a foreign key. |
| Results differ from what you expect | Enable DEBUG on the `celofast.km` logger to see the exact PQL of every request. See [Inspect the PQL that runs](knowledge-model-sdk.md#inspect-the-pql-that-runs). |

Printed metadata can contain business information; review the content before
sharing a diagnostic.

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
