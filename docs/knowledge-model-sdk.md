# Knowledge Models: typed business objects

[Documentation](index.md) · [Getting started](getting-started.md) · [API reference](api-reference.md) · [Migrating to 0.5](migration-0.5.md)

Celofast turns a Knowledge Model into a typed object SDK:

> **Definitions describe objects. Generated value classes represent loaded
> objects. The runtime retrieves objects and traverses relationships.**

```python
from generated.inventory import Plant, km as inventory

client = cf.km(inventory)

plant = client.objects(Plant).get("SAP_ECC::100::1000")
print(plant.country)                   # str | None, already loaded

page = (
    client.objects(Plant)
    .where(Plant.fields.country.eq("DE"))
    .fetch_page(page_size=100)
)
for plant in page.items:
    print(plant.key, plant.country)

materials = plant.links.materials.fetch_page(page_size=50)   # ObjectPage[MaterialMasterPlant]
home = materials.items[0].links.plant.fetch()                # Plant | None
```

There is no column selection, PQL, query dictionary, or DataFrame in this API.
Every read returns complete, validated, immutable objects.

| Expression | Meaning |
| --- | --- |
| `Plant.fields.country` | A typed field definition, `Field[str \| None]` |
| `Plant.fields.country.eq("DE")` | A predicate for a `Plant` collection |
| `plant.country` | A loaded Python value, `str \| None` |
| `plant.key` | This instance's business key (a tuple for composite keys) |
| `plant.ref` | `ObjectRef(source, object_type, key)` |
| `plant.links.materials` | A typed relationship collection, `ObjectCollection[MaterialMasterPlant]` |
| `material.links.plant` | A typed to-one relationship, `ToOne[Plant]` |

The examples use the mapping below; your class and field names derive from
your KM and mapping.

## 1. Describe your objects

Register the KM and its object mapping in your application's `pyproject.toml`:

```toml
[tool.celofast.knowledge-models.inventory]
space-id = "SPACE_ID"
package-id = "PACKAGE_ID"
key = "inventory-km"
mode = "draft"
output = "generated/inventory"

[tool.celofast.knowledge-models.inventory.mapping]
# Records that are not business objects (event logs, helper tables, ...).
exclude = ["EL_CELONIS_DELIVERYLINE", "MLFLOW_RUNS"]

[tool.celofast.knowledge-models.inventory.mapping.objects.O_CELONIS_PLANT]
class = "Plant"                        # optional; defaults to the display name
key = ["ID"]                           # attribute IDs; several IDs form a composite key

[tool.celofast.knowledge-models.inventory.mapping.objects.O_CELONIS_PLANT.links.materials]
target = "O_CELONIS_MATERIALMASTERPLANT"
cardinality = "many"
on = { ID = "PLANT_ID" }               # source attribute ID -> target attribute ID

[tool.celofast.knowledge-models.inventory.mapping.objects.O_CELONIS_MATERIALMASTERPLANT]
class = "MaterialMasterPlant"
key = ["ID"]
exclude-fields = ["SafetyStockLevelFormatted"]     # not loaded
types = { CurrentValuatedStockQuantity = "float" } # declare a missing type

[tool.celofast.knowledge-models.inventory.mapping.objects.O_CELONIS_MATERIALMASTERPLANT.links.plant]
target = "O_CELONIS_PLANT"
cardinality = "one"
on = { PLANT_ID = "ID" }
```

`mapping` may instead be a path to a TOML file with the same `exclude` and
`objects` keys, relative to `pyproject.toml`. The object IDs are captured record
IDs; field references are captured attribute IDs.

### Generation is strict

Every captured record must become an identified object type or be excluded.
`celofast km pull` lists every gap at once and generates nothing until each is
resolved:

| Situation | Required action |
| --- | --- |
| Record declares no identifier | Set `key`, or add the record to `exclude`. |
| Identifier expression matches no loaded attribute | Set `key`. |
| Attribute has no or an unknown `columnType` | Declare it in `types`, or add it to `exclude-fields`. |
| Attribute has no expression | Add it to `exclude-fields`. |
| Attribute ID appears in several collections | Add it to `exclude-fields`. |
| Key attribute is a `float` or `bool` | Choose another key. Keys are `str`, `int`, `date`, or `datetime`. |
| To-one link does not map exactly the target key | Map the key, or use `cardinality = "many"`. |
| Link fields differ in type or are not loaded | Fix the mapping. |

A record whose declared KM identifier resolves to a loaded attribute needs no
mapping entry. Celonis often projects the identifier as several attributes (for
example `ID` and `IDENTIFIER_AS_ATTRIBUTE`); matching expressions are the same
column, and the first in captured order becomes the key. Celofast never infers
a key from a field *name*, and a record's ID is never an instance's key.

Supported value types are `str`, `int`, `float`, `bool`, `date`, and
`datetime`. Every field is `T | None` except key fields, which are never null.

## 2. Pull and import

```bash
uv run celofast km pull inventory
```

Or explicitly, with a mapping file:

```bash
uv run celofast km pull --space-id SPACE_ID --package-id PACKAGE_ID --km inventory-km --mode draft --output generated/inventory --mapping inventory-objects.toml
```

The generated package contains:

| File | Content |
| --- | --- |
| `__init__.py` | Exports every value class and `km`, the object registry, plus the `__celofast__` generation stamp. |
| `definitions.py` | The KM source, then `PlantDefinition` classes with `Field[...]` members, expressions, keys, and link declarations. |
| `objects.py` | `Plant` value classes and the `km` registry. |
| `links.py` | `PlantLinks` (instance traversal) and `PlantRelations` (relationship predicates) classes. |
| `py.typed` | Marks the package as typed. |

The package is plain Python with no data files. Everything the runtime needs is
written as literals: the KM source, Data Model, and each field's expression and
metadata. The captured KM definition is only the input to generation, so parts
of the KM that no generated type uses (KPIs, filters, excluded records and
fields) are not in the package.

A generated value class and its definition look like this:

```python
@dataclass(frozen=True, kw_only=True)
class PlantDefinition(_d.ObjectDefinition):
    'Plant'
    id: _d.Field[str]
    country: _d.Field[str | None]
    ...


@dataclass(frozen=True, kw_only=True)
class Plant(_o.Object):
    'Plant'
    key: str
    id: str
    country: str | None
    ...

    fields: ClassVar[_defs.PlantDefinition] = _defs._Plant
    relations: ClassVar[_links.PlantRelations] = _links.PlantRelations()

    @property
    def links(self) -> _links.PlantLinks:
        return _links.PlantLinks(self)
```

Importing is offline: it does not authenticate, contact Celonis, or import
PyCelonis or pandas. Imports verify the runtime version.

### Definitions

`Plant.fields` describes the type. Iterate it for all fields, or look one up by
its exact captured attribute ID:

```python
Plant.fields.object_type               # "O_CELONIS_PLANT"
Plant.fields.key_fields                # (Plant.fields.id,)
Plant.fields.links["materials"]        # LinkDefinition(target=..., cardinality="many", ...)
Plant.fields["COUNTRY"] is Plant.fields.country
Plant.fields.country.value_type        # "str"
Plant.fields.country.expression        # '"o_celonis_Plant"."Country"'
Plant.fields.country.description       # captured display name and description
Plant.fields.metadata                  # {"displayName": "Plant", "description": None}
inventory.source                       # tenant, Space, Package, KM key, lifecycle
inventory.variables                    # ${name} KM inputs used by generated fields
```

Field names come from the attribute's data-model column name when it spells
the same identifier (`ISDISCONTINUED` with column `IsDiscontinued` becomes
`is_discontinued`), and otherwise from the attribute ID. Only `key`, `ref`,
`links`, `relations`, `fields`, `model`, `object_type`, `metadata`, and
`key_fields` are reserved. An attribute with a reserved or colliding Python
name receives a readable suffix, such as `key_attribute`; each generated field
keeps its attribute ID (`Plant.fields["KEY"]`).

## 3. Retrieve objects

`cf.km(inventory)` validates the tenant, Space, Package, lifecycle, KM key, and
Data Model, then returns a `KnowledgeModelClient`. `client.objects(Plant)`
returns an immutable `ObjectCollection[Plant]`.

| Operation | Behavior |
| --- | --- |
| `collection.get(key)` | One object; raises `ObjectNotFoundError` if absent. Composite keys are tuples. |
| `collection.where(*predicates)` | A narrower collection; predicates combine with AND. |
| `collection.order_by(*sorts)` | A reordered collection: `Type.fields.x.asc()`/`.desc()`, or a field (ascending). The key breaks ties. |
| `collection.fetch_page(page_size=100, *, offset=0)` | `ObjectPage` in the requested order, then key order. `page_size` is 1–10,000. |
| `page.items`, `iter(page)`, `len(page)` | The loaded objects. |
| `page.has_more`, `page.next_page()` | Whether more objects exist; fetch the following page or `None`. |

Offsets page over live data, so concurrent changes can move objects between pages.

### Predicates

Predicates are built from definitions and combine with `&`, `|`, and `~`:

```python
stock = MaterialMasterPlant.fields

below_safety_stock = (
    stock.is_discontinued.eq(0)
    & stock.current_valuated_stock_quantity.lt(stock.safety_stock_quantity)
)
```

| Expression | Meaning |
| --- | --- |
| `f.eq(x)`, `f.ne(x)` | Equal / not equal. `None` is a value: `eq(None)` matches nulls, `ne(None)` non-nulls, and a null differs from every value. |
| `f.lt(x)`, `f.lte(x)`, `f.gt(x)`, `f.gte(x)` | Ordering. False when either side is null; `None` is rejected. Booleans have no ordering. |
| `f.lt(other_field)` | Field-to-field comparison on the same type; `int` and `float` compare with each other. |
| `a & b`, `a \| b`, `~a` | And, or, and exact complement: `~f.eq(x)` is `f.ne(x)`, including nulls. |
| `Type.relations.one.has(p)` | The related object of a to-one link exists (and matches `p`, if given). |
| `Type.relations.many.any(p)` | At least one related object of a to-many link exists (and matches `p`, if given). |

Values are validated against the field's type when the predicate is created.
Combining predicates of different types is rejected. Reach related objects
through `relations` instead. Predicates are plain values, so business rules can
be named, reused, and nested:

```python
external_purchase = PurchaseDocument.fields.is_canceled.eq(0) & (
    PurchaseDocument.relations.vendor.has(Vendor.fields.is_internal_vendor.eq(0))
)
active_external_line = PurchaseDocumentLine.fields.is_canceled.eq(0) & (
    PurchaseDocumentLine.relations.header.has(external_purchase)
)
overdue = (
    client.objects(PurchaseScheduleLine)
    .where(
        schedule.expected_delivery_date.lt(as_of)
        & schedule.received_quantity.lt(schedule.expected_quantity)
        & PurchaseScheduleLine.relations.purchase_document_line.has(active_external_line)
    )
    .order_by(schedule.expected_delivery_date.asc())
    .fetch_page(page_size=100)
)
```

A relationship predicate is resolved before the object read. Celofast first
reads the linked values of the related objects that match, innermost relation
first, then tests the source field against them. It follows the declared link
mapping, not Data Model joins. It requires a single-field link, and a relation
may match at most 10,000 related values; beyond that it raises
`QueryValidationError` asking for a narrower predicate. A null source value
never matches, so `~relations.x.any(...)` includes objects without related
objects.

[tests/inventory_rules.py](../tests/inventory_rules.py) contains three complete
inventory rules (safety stock without firm supply, overdue external schedules,
and alternative source plants). They are verified in
[tests/test_inventory_rules.py](../tests/test_inventory_rules.py), both offline
and, when enabled, against Celonis.

### What a read guarantees

- **Complete snapshots.** Every read loads the key and every generated field.
  There is no partial loading, so an unloaded value can never look like `None`.
- **Identity.** Keys must be non-null. Rows with the same key but different
  values raise `ObjectIdentityError`; each property must resolve to one value
  per key.
- **Decoded values.** Values are checked against the declared type and returned
  as plain Python values. A date with a time component, a non-integral `int`, or
  a string where a number is declared raises `ObjectValueError`.
- **Failures are failures.** A failed export raises the native PyCelonis error
  with its cause chain; it never becomes an empty page.
- **No hidden requests.** Reading `plant.country`, `plant.key`, `plant.ref`, or
  building `plant.links.materials` never contacts Celonis. Only `get`,
  `fetch_page`, `next_page`, and `ToOne.fetch` do.

Objects are frozen dataclasses: they compare by value and work with
`dataclasses.asdict`. The client that loaded an object is attached privately so
its relationships can be fetched; it is not a field.

### Relationships

Generated accessors exist only for declared links:

```python
materials = plant.links.materials                  # ObjectCollection[MaterialMasterPlant]
external = materials.where(MaterialMasterPlant.fields.procurement_type.eq("F"))
plant = material.links.plant.fetch()               # Plant | None
```

A to-many link is an ordinary collection filtered by the link mapping, so it
supports `where`, `get`, and paging. A to-one link maps exactly the target key,
so it resolves to at most one object. A null source value returns an empty page
or `None` without a request.

### KM input variables

Captured expressions can contain `${name}` placeholders for KM input variables.
`inventory.variables` lists the ones generated fields use. Bind them
explicitly per client:

```python
client = cf.km(inventory, variables={"im_consideredpastmonths": "12"})
```

Bindings are exact PQL text. Quote text yourself where the expression expects a
literal (for example `"'Average'"`). A read that needs an unbound placeholder
raises `UnresolvedVariableError` before any request. Bindings apply to captured
field expressions only; cloud dependencies such as another record's calculated
attribute resolve with the KM's own values in Celonis. If a dependency fails
there, exclude the affected fields.

## 4. Review changes and check CI

```bash
uv run celofast km pull inventory --check
```

Check reads the cloud definition, regenerates the package in memory, and prints
a unified diff of every generated file that would change, without writing.
Drift is exactly what changes the generated code: expressions, types, names,
keys, links, metadata, or the mapping. Edits to parts of the KM that no
generated type uses are not drift. A new record the mapping doesn't cover still
fails the check. Exit **0** means up to date, **1** means drift, and **2** means
failure, including an incomplete mapping.

Changing the mapping requires a pull: generation always starts from the current
cloud definition.

Keep application code outside the generated directory. Celofast refuses to
replace unrelated files, verifies the new package imports before installing it,
and restores the previous package if replacement fails. Restart Python after
pulling so every generated module is reloaded together.

## What this SDK does not do

- No aggregation, grouping, KPI selection, arbitrary PQL filters, or DataFrames.
  Tables configured in a View remain available through
  [Views and inputs](views-and-inputs.md).
- No writes. Future write support will expose explicit supported actions, not a
  generic `save()`.
- No projections or partial objects. Predicates select objects; every read
  still returns complete, typed instances.
