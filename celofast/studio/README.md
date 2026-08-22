# Celofast Studio View Table Reader

This folder contains a reusable component for reading data configured in a
published Celonis Studio View. It does not scrape the browser. It parses the
View's published `serialized_content`, compiles visible table columns and
filters into PQL, resolves Knowledge Model references and View variables, and
executes the query against the assigned Data Model.

Execution uses the current SaolaPy API:

```python
DataFrame.from_pql(query, data_model=data_model).to_pandas()
```

The component does not instantiate `KnowledgeModelSaolaConnector` directly.

The reader is part of the `celofast` package and reuses Celofast's shared
authenticated client factory. It does not scrape the browser or import
application-specific code.

Install it as part of the project with `uv sync` (or `pip install -e .`). The
package requires the PyCelonis and SaolaPy versions declared in the root
`pyproject.toml`.

## Quick start

```python
from celofast import CelonisViewReader

reader = CelonisViewReader.from_studio(
    space_id="your-space-id",
    package_id="your-package-id",
    view_key="operations-view",
)

orders_df = reader.read("Orders")
events_df = reader.read(
    "Events",
    inherit_filters_from=("Orders",),
)
```

`inherit_filters_from` is useful when one table query must inherit filters
configured on another table in the same View.

## Constructing from existing objects

Projects that already resolved their Celonis objects can avoid a second lookup
by passing the client explicitly:

```python
from celofast import CelonisViewReader, get_celonis

reader = CelonisViewReader(
    view=view,
    knowledge_model=knowledge_model,
    data_model=data_model,
    variables={"lookback_days": 30},
)
```

For an already configured client, the equivalent factory call is:

```python
reader = CelonisViewReader.from_studio(
    get_celonis(),
    space_id="your-space-id",
    package_id="your-package-id",
    view_key="operations-view",
)
```

If `variables` is omitted, API-visible defaults are read from the View's
`input_variable_definitions`. User-specific values are generally not visible
to service/API credentials; use system-scoped variables or pass values
explicitly.

## Build, inspect, and execute separately

Query construction and execution are intentionally separate operations:

```python
query = reader.build_query("Orders")
orders_df = reader.execute(query)
```

SaolaPy validates the generated columns and filters against the Data Model and
raises its native errors. The component does not duplicate that validation or
wrap those errors.

## Public API

- `CelonisViewReader.from_studio(...)` resolves the View, Knowledge Model,
  Data Model, and Data Pool from Celonis Studio.
- `CelonisViewReader.build_query(...)` compiles a View table to PQL without
  executing it.
- `CelonisViewReader.read(...)` compiles and executes one table.
- `CelonisViewReader.resolved_filters(...)` exposes resolved filter PQL for
  composition or inspection.
- `CelonisViewReader.execute(...)` validates and executes a generated query
  through SaolaPy.

## Design choices

- Missing KPI/filter references fail with a clear error instead of silently
  dropping a filter and returning a broader dataset.
- A table may legitimately have zero filters.
- Hidden View columns are not queried.
- Parsing, PQL resolution, and context discovery are separate from SaolaPy
  execution.
- There are no global paths, notebook assumptions, naming rules, or print side
  effects in the reusable core.

## Run the component tests

```bash
uv run pytest
```
