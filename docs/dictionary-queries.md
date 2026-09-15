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
`to_query()` retains them to preserve source metadata;
it does not turn them into JSON. Replacing an object with `.pql` makes it a raw
string and discards source validation for that expression. Explicit bindings
are required for placeholders in both forms.

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

Raw and generated PQL placeholders need explicit bindings. Missing values raise
`UnresolvedVariableError`, even when captured metadata contains a default. See
[KM execution semantics](knowledge-model-sdk.md#query-behavior).

## Mix generated objects with existing dictionaries

After [pulling a KM](knowledge-model-sdk.md#configure-and-pull):

```python
from generated.inventory import km as inventory

km = cf.km(inventory)
plant = inventory.records.o_celonis_plant

result = km.execute({
    "columns": {
        "Plant": plant.number_formatted,
        "Live KPI": 'KPI("inventory_value")',
    },
    "filters": [plant.country.eq("DE")],
}, limit=100)
```

Generated KPIs contribute their captured `.pql` expression. A raw `KPI(...)`
call uses the live KM reference, including its native filter/parameter
semantics. Capturing a definition does not freeze the dependencies it refers to.

## Validation and native errors

The builder and dictionary API share compilation, explicit variable binding,
source checks, and execution. They reject invalid shapes, object categories,
empty expressions, incompatible sources, and invalid execution options locally.
Captured objects are checked against the connected KM and Data Model at compilation.

Celonis validates PQL syntax and semantics. Native PyCelonis/SaolaPy execution
errors propagate unchanged with their cause chains.

Inspect the query sent to PyCelonis with `km.build(query, variables=...)`.
For deeper failures, see [Troubleshooting](troubleshooting.md).
