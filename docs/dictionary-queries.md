# Dictionary queries and raw PQL

[Documentation](index.md) · [Typed KM queries](knowledge-model-sdk.md)

Use a dictionary when you already have PQL, want to store query definitions as
configuration, or need to consume a query exported from a View. Generation is
optional for this API.

## Execute a reusable definition

Configure authentication as described in [Getting started](getting-started.md).
Replace the IDs, KM key, and PQL names in this example with your own:

```python
from celofast import CeloFast, QueryDefinition

cf = CeloFast("SPACE_ID", "PACKAGE_ID")
km = cf.km("inventory-km")

query: QueryDefinition = {
    "columns": {
        "Plant": '"Plant"."Number"',
        "Value": 'KPI("inventory_value")',
    },
    "filters": [
        'FILTER "Plant"."Country" = \'DE\';',
        "FILTER @active_inventory;",
    ],
    "order_by": [
        {"pql": 'KPI("inventory_value")', "ascending": False},
    ],
}

native_pql = km.build(query)
result = km.execute(query, limit=100, offset=0, distinct=True)
```

`build()` returns native PyCelonis PQL without executing it. `execute()` returns
a pandas DataFrame. Omitting `limit` requests all matching rows. Filters combine
with AND, and columns retain their dictionary insertion order.

## Definition fields

| Field | Required | Value |
| --- | --- | --- |
| `columns` | Yes | Non-empty mapping of output names to PQL strings, generated attributes, or generated KPIs. |
| `filters` | No | List of complete PQL filter strings, generated KM filters, or attribute equality predicates. |
| `order_by` | No | List of mappings with `pql` and optional `ascending`. The latter defaults to `True`. |

Unknown fields are rejected. Put `limit`, `offset`, `distinct`, and `variables`
in method arguments, not in the dictionary. Aliases must be non-empty strings;
expressions must have non-empty PQL. Execution limits and offsets must be
non-negative integers, excluding booleans.

## Serialize plain-string definitions

The example above contains only JSON-compatible values:

```python
import json

saved_query = json.dumps(query, indent=2)
restored_query = json.loads(saved_query)
result = km.execute(restored_query, limit=100)
```

Generated attributes and predicates are Python objects. A builder's
`to_query()` retains them to preserve source metadata and captured defaults;
it does not turn them into JSON. Replacing an object with `.pql` makes it a raw
string and changes its template-binding behavior. Do so only when you also
intend to manage the necessary bindings yourself.

## Bind raw template variables

`${name}` replacement is textual. Supply exact PQL fragments, including quotes
when the replacement is a string literal:

```python
query = {
    "columns": {"Plant": '"Plant"."Number"'},
    "filters": ['FILTER "Plant"."Country" = ${country};'],
}

result = km.execute(query, variables={"country": "'DE'"}, limit=100)
```

For Python values in typed queries, prefer `plant.country.eq("DE")`; it handles
literal encoding. `variables=` is not a parameterized query interface. It does
not automatically quote or escape user-provided text, and it does not update
server-managed KM variables or View controls.

Raw PQL placeholders need explicit bindings. Missing values raise
`UnresolvedVariableError`. Generated objects instead use their captured string
defaults before explicit overrides, as described in the
[KM variable guide](knowledge-model-sdk.md#query-behavior).

## Mix generated objects with existing dictionaries

After [pulling a KM](knowledge-model-sdk.md#configure-and-pull):

```python
from generated.inventory import km as inventory

km = cf.km(inventory)
plant = km.records.o_celonis_plant

result = km.execute({
    "columns": {
        "Plant": plant.attributes.number_formatted,
        "Live KPI": 'KPI("inventory_value")',
    },
    "filters": [plant.country.eq("DE")],
}, limit=100)
```

Generated KPIs contribute their captured `.pql` expression. A raw `KPI(...)`
call uses the live KM reference, including its native filter/parameter
semantics. Capturing a definition does not freeze the dependencies it refers to.

## Validation and native errors

The dictionary API validates the definition's shape, expressions, variables,
and execution options. It preserves native PyCelonis/SaolaPy execution errors.
It does not apply the builder's additional local PQL structure checks or
per-expression source checks. Use the [query builder](knowledge-model-sdk.md)
when you want those checks.

Inspect the query sent to PyCelonis with `km.build(query, variables=...)`.
For deeper failures, see [Troubleshooting](troubleshooting.md).
