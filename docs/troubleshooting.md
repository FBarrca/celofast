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
| A record or field you need is missing | Look under `# Not generated:` at the top of the generated `objects.py` for the reason. A record without a primary key needs `key = ["ID"]`; an untyped attribute needs `types`; an attribute that fails in Celonis must be fixed in the KM, then pulled again. |
| Pull refuses the output directory | Keep application code outside the managed directory. Use a separate output for a different KM source. |
| `ModuleNotFoundError` for `generated.inventory` | Run the configured pull and make its output importable from the application's working directory or package. |
| `SDKCompatibilityError` on import | The package was generated for another runtime (for example the 0.4 query API). Rerun `celofast km pull` and restart Python; keep all generated files together. |
| A field has an unexpected name | Reserved or colliding names get suffixes, such as `key_attribute`; the generated `objects.py` lists each field with its attribute ID. Look fields up by attribute ID with `Plant.fields["ID"]`. |
| `TypeError` from `cf.km("key")` | Pass the generated model: `cf.km(inventory)`. Use `cf.augmentation_tables("key")` for output tables. |
| `QueryValidationError` about source or Data Model | Connect to the matching Space, Package, lifecycle, and Data Model. |
| Cloud edits are missing after pull | Restart Python so every generated module reloads with the new capture. |

## Retrieving objects

| Symptom | Check / next step |
| --- | --- |
| `ObjectNotFoundError` | No object has that key. Composite keys are tuples in key-field order (`Plant.fields.key_fields`). |
| `ObjectIdentityError` | The key is null, or one key produced different values. The key is not unique for that record, or a field's expression joins to several rows; choose another key or exclude the field. |
| `ObjectValueError` | A retrieved value does not match the declared type, or a filter value has the wrong type. Pull again if the KM changed, or pass a value of the field's type. |
| `UnresolvedVariableError` | A loaded field uses a `${name}` KM input variable that has neither a value nor a default in the KM. Set one in Studio, or exclude the field. |
| `QueryValidationError` from `where()` | Use predicates from the collection's own class, such as `Plant.fields.country.eq(...)`. Raw PQL is not accepted. |
| Native export error, such as an error in another record's calculated attribute | A loaded field depends on a definition that fails in Celonis. Inspect the exception chain and exclude the affected fields until the KM is fixed. |
| Python `and`/`or` on predicates raises an error | Pass several predicates to `where()` or chain calls; they combine with AND. |
| Results differ from what you expect | Enable DEBUG on the `celofast.km` logger to see the exact PQL of every request. See [See the PQL that runs](knowledge-model-sdk.md#10-see-the-pql-that-runs). |

Printed metadata can contain business information; review the content before
sharing a diagnostic.

## Views and controls

| Symptom | Check / next step |
| --- | --- |
| `ComponentNotFoundError` or `AmbiguousComponentError` | List `view.elements` and select the element by its component ID. Names are case-sensitive. |
| `ComponentVariableError` | The input field isn't bound to a variable the KM or View defines. Check the field's input variable in Studio. |
| `variable_key` fails on a range date picker | A range has two variables: use `start_variable_key` and `end_variable_key`, or `.value` for a `DateRange`. |
| An input's value differs from what a user sees in the browser | The input variable is user-specific (`USER_SPECIFIC`): each user has their own value, and Celofast can only read its own. Make the variable global (scope `SYSTEM`) in Studio. See [Whose value?](views.md#4-read-an-input-field). |
| `UnresolvedVariableError` from `rows()` | The table uses an input with neither a value nor a default. Set one in Studio. |
| A View input doesn't filter KM objects | Reading an input doesn't filter KM objects; use its value in a predicate. View tables use input values automatically. |
| `ResourceResolutionError` for an input | Celonis returned no value, or an unreadable one. Dates must be ISO dates or epoch timestamps; checkboxes must be `true` or `false`. |

## Augmentation writes

| Symptom | Check / next step |
| --- | --- |
| A lazy reference succeeds but its first operation fails | `table()` does not verify existence. Create the table explicitly or correct its name. |
| `AugmentationValidationError` | Check DataFrame columns, keys, foreign-key pairs, and `batch_size` in [Augmentation tables](augmentation-tables.md). |
| A draft write affects another consumer | Writes target the shared Data Model table; draft/published mode does not isolate them. |
| A later batch fails | Earlier batches and the schema may already exist. Inspect remote state before retrying; there is no automatic rollback. |
| A new column does not appear after upsert | Upsert does not extend the existing schema. Plan schema changes through the appropriate native/platform workflow. |
| Native API, quota, or permission error | Check the tenant's augmentation API availability, Data Model write access, and service-level limits. |
