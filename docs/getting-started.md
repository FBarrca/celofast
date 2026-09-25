# Getting started

[Documentation](index.md) · Next: [Knowledge Models](knowledge-model-sdk.md)

This guide takes you from installation to a small live query. Replace every
uppercase placeholder with a value from your tenant. The later KM examples
assume an Inventory KM; use the names generated from your own definitions.

## 1. Install in your application

Celofast requires Python 3.10 or newer. It declares pinned PyCelonis and SaolaPy
dependencies in [pyproject.toml](../pyproject.toml).

Using uv:

```bash
uv add "celofast @ git+https://github.com/FBarrca/celofast.git"
```

The `celofast` command is available in that environment after installation.
Examples use `uv run` to select the application's environment. With an already
activated environment, omit that prefix.

Use the repository's uv configuration when developing Celofast: it includes
wheel sources for the pinned Celonis dependencies. See
[Development](development.md) for the checkout workflow.

## 2. Configure authentication

### Use the built-in OAuth client

Create `.env` in your application's working directory, following
[.env.example](../.env.example):

```dotenv
CELONIS_URL=https://YOUR_TENANT.celonis.cloud
OAUTH_CLIENT_ID=YOUR_CLIENT_ID
OAUTH_CLIENT_SECRET=YOUR_CLIENT_SECRET
OAUTH_SCOPES=YOUR_GRANTED_SCOPES
```

All four values are required by the built-in client factory. `OAUTH_SCOPES`
must contain the scopes granted to your OAuth client for the operations you
use. The client needs access to the selected Space and Package and, for KM
queries, their Data Model through its accessible Data Pool. Augmentation writes
also require permission to modify that Data Model's augmentation tables.

The factory searches for `.env` from the current working directory and also
accepts environment variables supplied by your runtime. Keep real credentials
out of source control; this repository ignores `.env`.

### Supply an existing PyCelonis client

If your application already authenticates PyCelonis, pass its `Celonis`
instance. The built-in OAuth factory is then bypassed:

```python
from celofast import CeloFast

# existing_client is your already-authenticated pycelonis.celonis.Celonis.
cf = CeloFast("SPACE_ID", "PACKAGE_ID", client=existing_client)
```

This is also the path for authentication methods managed outside Celofast.

## 3. Select a Space, Package, and lifecycle

```python
from celofast import CeloFast

cf = CeloFast(
    space_id="SPACE_ID",
    package_id="PACKAGE_ID",
    mode="draft",
)
```

| Setting | Meaning |
| --- | --- |
| `space_id` | Exact Space ID in the selected lifecycle context. |
| `package_id` | Exact Package ID in that Space. |
| `mode="draft"` | Studio draft resources; this is the default. |
| `mode="published"` | Published Apps resources. Use the corresponding published IDs. |

Space/Package IDs and KM/View keys are explicit arguments or pull configuration;
Celofast does not read them from environment variables. A missing published
resource does not fall back to its Studio draft.

## 4. Describe and generate your KM objects

Add this table to your application's `pyproject.toml`, using the exact KM key
(not its display name):

```toml
[tool.celofast.knowledge-models.inventory]
space-id = "SPACE_ID"
package-id = "PACKAGE_ID"
key = "inventory-km"
mode = "draft"
output = "generated/inventory"
```

Generate the object package. Object types, keys, field types, and links are
derived from the KM and its Data Model; no mapping is needed:

```bash
uv run celofast km pull inventory
```

The command shows progress while it reads Data Model columns and test-runs
calculated attributes, then prints how many object types and links it
generated. Anything it skipped is listed under `# Not generated:` in the
generated `objects.py`. To rename classes or links, or change other choices, see
[Customize what is generated](knowledge-model-sdk.md#10-customize-what-is-generated).

## 5. Retrieve your first objects

```python
from generated.inventory import Plant, km as inventory

client = cf.km(inventory)
page = client.objects(Plant).fetch_page(page_size=5)
for plant in page.items:
    print(plant.key, plant.country)
```

Run from a directory where `generated` is importable, or package that directory
with your application. Use your editor's autocomplete for your actual class and
field names. The import itself is offline; `cf.km(inventory)` validates the
package's source against the connected KM and its Data Model. The result is a
page of immutable `Plant` objects with plain Python values.

This confirms the authentication, resource selection, Data Model access, and
read path. See [Troubleshooting](troubleshooting.md) if one of those steps fails.

Continue with the [KM guide](knowledge-model-sdk.md) for filters, sorting,
relationships, input variables, and keeping the package up to date.

## Next steps

- [Views](views.md): read a View's tables and input fields.
- [Augmentation tables](augmentation-tables.md): write your results back to Celonis.
- [API reference](api-reference.md): look up arguments and return types.
