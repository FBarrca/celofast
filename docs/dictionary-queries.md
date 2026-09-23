# View query dictionaries

[Documentation](index.md) · [Views and inputs](views-and-inputs.md)

View tables export their configured query as a plain dictionary. This is part
of the View feature. The [Knowledge Model object SDK](knowledge-model-sdk.md)
does not accept or return query dictionaries.

## Export and inspect a table query

```python
table = cf.view("operations-view").table("Orders")
query = table.to_query(extra_filters=['FILTER "Plant"."Country" = \'DE\';'])
```

| Field | Value |
| --- | --- |
| `columns` | Non-empty mapping of output names to PQL strings, in table order. |
| `filters` | Complete PQL filter strings: the table's own, then inherited, then extra filters. |
| `order_by` | List of mappings with `pql` and optional `ascending` (default `True`). |

`to_query()` returns a fresh dictionary containing only strings, so it can be
serialized as JSON or YAML. KPI and KM filter references such as
`FILTER @active_inventory;` remain symbolic for server-side resolution.

## Bind template variables

`${name}` replacement is textual. Supply exact PQL fragments, including quotes
when the replacement is a string literal:

```python
result = table.execute(variables={"country": "'DE'"}, limit=100)
```

Bindings merge after published View input defaults and View-level variables.
They do not automatically quote user text, update View controls, or override
server-managed KM variables. A missing binding raises `UnresolvedVariableError`.

## Validation and native errors

Unknown fields, empty expressions, duplicate aliases, and invalid execution
options are rejected locally. Celonis validates PQL syntax and semantics;
native PyCelonis/SaolaPy errors propagate unchanged with their cause chains.
For deeper failures, see [Troubleshooting](troubleshooting.md).
