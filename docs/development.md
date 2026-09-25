# Development and documentation

[Documentation](index.md) · [Project overview](../README.md)

## Work on the repository

From a checkout of Celofast:

```bash
uv sync
uv run pytest
```

The lockfile and [pyproject.toml](../pyproject.toml) define the development
environment, including wheel sources for the pinned Celonis packages. The
offline tests use local fixtures and mocks. They cover mapping validation, generation, typing,
object hydration, native connector delegation, validation, Views, controls, and output batching.
Live tests also run when credentials are configured in `.env` or the environment.

For a targeted KM change:

```bash
uv run pytest tests/test_sdk_generate.py tests/test_object_runtime.py tests/test_inventory_rules.py tests/test_sdk_typing.py
```

## Repository map

| Location | Responsibility |
| --- | --- |
| [client.py](../celofast/client.py) | OAuth client creation and caching. |
| [core.py](../celofast/core.py), [resolution.py](../celofast/resolution.py) | Package scope, lifecycle selection, lookup and caches. |
| [sdk/capture.py](../celofast/sdk/capture.py) | KM and Data Model captures and retrieval. |
| [sdk/mapping.py](../celofast/sdk/mapping.py) | Normalization: object mappings, keys, value types, and links. |
| [sdk/definitions.py](../celofast/sdk/definitions.py), [sdk/objects.py](../celofast/sdk/objects.py) | Offline definitions (`Field`, `ObjectDefinition`); loaded objects, collections, pages, and links. |
| [sdk/planning.py](../celofast/sdk/planning.py), [sdk/hydration.py](../celofast/sdk/hydration.py) | Private read planning; identity and value validation. |
| [sdk/generate.py](../celofast/sdk/generate.py), [sdk/package.py](../celofast/sdk/package.py), [sdk/loading.py](../celofast/sdk/loading.py) | Generated packages, safe installation, drift reporting, and runtime compatibility. |
| [query.py](../celofast/query.py) | View query dictionaries, explicit binding, and native PQL compilation. |
| [resources](../celofast/resources) | KM client and connection, View, control, and augmentation-table handles. |
| [cli.py](../celofast/cli.py) | `celofast km pull` and `--check`. |
| [tests](../tests) | Local tests and credential-enabled cloud checks. |
| [docs](.) | Markdown guides and references. |

## Live integration tests

Live tests use the repository's `.env` for the usual `CELONIS_URL` and `OAUTH_*`
credentials (see [.env.example](../.env.example)); existing environment variables
take precedence. They read the `inventory` KM configuration from
[pyproject.toml](../pyproject.toml), including its mode and mapping file.
No separate test environment variables are needed. Both live suites run when
credentials are available and skip when they are missing. They only read cloud data
and generate packages in temporary directories.

Then run:

```bash
uv run pytest tests/test_sdk_live.py
```

[test_inventory_acceptance.py](../tests/test_inventory_acceptance.py) holds
online end-to-end acceptance tests. They run as part of `uv run pytest` whenever
Celonis credentials are configured (`.env`). They run the real
`celofast km pull inventory` into a temporary directory, execute the documented
inventory questions exactly as an application writes them, and assert both the
API (typed objects, generated names) and the values: every result satisfies the
rule (checked through its links), and nothing is missing (checked in plain
Python over every loaded object). They take about six minutes and only read
data. Exclude them with:

```bash
uv run pytest -m "not live"
```

[test_inventory_rules.py](../tests/test_inventory_rules.py) runs the same
questions offline over hand-built objects that cover every branch.

After changing `inventory-objects.toml` or the derivation rules, refresh the
offline fixture (this reads the live KM, so it needs credentials) with
`uv run python tests/fixtures/build_inventory_fixture.py`. It captures exactly
what `celofast km pull` does (Data Model tables, primary keys, column types,
foreign keys, and validation results) for the seven object types the offline
tests use.

[test_sdk_live.py](../tests/test_sdk_live.py) checks package generation, drift,
import, and a small page of `Plant` objects from the same configured Inventory KM.

## Maintain the Markdown docs

The [README](../README.md) is the short entry point. The [documentation
index](index.md) routes readers to task guides. Keep detailed behavior in the
relevant guide and signatures in the [API reference](api-reference.md).

When changing an API:

1. Update its guide, reference entries, and relevant README example together.
2. Check signatures and return values against the implementation.
3. Use explicit placeholders and name any data or client a snippet assumes
   already exists. Keep tenant credentials out of examples.
4. Validate Python/TOML snippets and relative links. Preview headings, tables,
   and code fences in a Markdown renderer.
5. Run tests relevant to any changed executable behavior.

No site generator or hosting configuration is needed. The practical
[augmentation guide](augmentation-tables.md) sits alongside the preserved
[architecture and limit notes](Augmentated_tables.md) and
[detailed platform reference](Augmentated_tables%20copy.md). Keep this research
and its source links when updating the guides; explain version differences
without removing the original findings.

## Generated application packages

Application-generated KM packages contain `__init__.py`, `objects.py`, and
`py.typed`: plain Python with no data files. Change definitions in the source
KM or the object mapping, pull again, and review the diff rather than editing
generated files.

For each object type, `objects.py` holds a definition class of `Field`s
(`PlantDefinition`), a frozen value dataclass (`Plant`), and, when the type has
relationships, a `Links` class (`PlantLinks`) that declares each relationship
once.

Compatibility has one checkpoint: `objects.py` calls
`require_runtime(RUNTIME_API_VERSION)`, so a package generated for another
runtime fails at import with a regeneration message. Bump
`RUNTIME_API_VERSION` in `celofast/sdk/loading.py` whenever generated code
needs a different runtime. There are no shims for older layouts; regenerate
instead.

The installer recognizes its own output by the `__celofast__` stamp in
`__init__.py` (`managed_by` and the KM `source`). It refuses directories without
the stamp, directories containing other files, and packages pulled from a
different KM. Delete such a directory to regenerate it.

Run `uv run celofast km pull inventory --check` in an application that has that
KM configured to verify drift. This is a cloud read and needs its credentials;
it is different from running the repository's local tests.
