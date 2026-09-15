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
normal test suite uses local fixtures and mocks. It covers generation, typing,
native connector delegation, validation, Views, controls, and output batching.

For a targeted KM change:

```bash
uv run pytest tests/test_builder.py tests/test_record_queries.py tests/test_sdk_typing.py
```

## Repository map

| Location | Responsibility |
| --- | --- |
| [client.py](../celofast/client.py) | OAuth client creation and caching. |
| [core.py](../celofast/core.py), [resolution.py](../celofast/resolution.py) | Package scope, lifecycle selection, lookup and caches. |
| [sdk](../celofast/sdk) | Capture, immutable objects, generation, package integrity, and drift reporting. |
| [builder.py](../celofast/builder.py), [expressions.py](../celofast/expressions.py) | Immutable composition and attribute equality predicates. |
| [query.py](../celofast/query.py) | Shared query validation, explicit binding, and native PQL compilation. |
| [resources](../celofast/resources) | KM, View, control, and augmentation-table handles. |
| [cli.py](../celofast/cli.py) | `celofast km pull` and `--check`. |
| [tests](../tests) | Local tests and opt-in cloud checks. |
| [docs](.) | Markdown guides and references. |

## Live integration tests

Live tests are opt-in. They use real credentials and read cloud KM data.
Configure the usual OAuth environment plus these process environment variables:

```dotenv
CELOFAST_LIVE_KM=1
CELOFAST_LIVE_SPACE_ID=SPACE_ID
CELOFAST_LIVE_PACKAGE_ID=PACKAGE_ID
CELOFAST_LIVE_KM_KEY=inventory-km
CELOFAST_LIVE_RECORD_ID=O_CELONIS_PLANT
CELOFAST_LIVE_ATTRIBUTE_ID=NumberFormatted
```

Then run:

```bash
uv run pytest tests/test_sdk_live.py
```

The live suite is skipped unless `CELOFAST_LIVE_KM=1` is set when tests are
collected. Inspect [test_sdk_live.py](../tests/test_sdk_live.py) before selecting
its resources; these checks do not validate every tenant-specific example.

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

Application-generated KM packages contain `__init__.py`, `capture.json`,
`schema.json`, and `py.typed`. Keep all four together. Change definitions in the
source KM, pull again, and review the diff rather than editing generated files.

The generator emits frozen dataclasses with typed fields for records and
root collections. Each record declares one flat set of business fields. A private
builder wires one object per captured path; the shared Record API handles
iteration and exact-ID lookup over those same fields. Keep construction separate from class
declarations so the generated API is easy to scan. Generated navigation needs no
properties or constructor-binding defaults; stored children preserve the old
hierarchy when a package is reloaded. Generator version 7 uses
runtime API version 5; regenerate packages after upgrading.

Run `uv run celofast km pull inventory --check` in an application that has that
KM configured to verify drift. This is a cloud read and needs its credentials;
it is different from running the repository's local tests.
