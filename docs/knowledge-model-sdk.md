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
| `plant.links.materials` | A typed relationship collection, `ObjectCollection[MaterialMasterPlant]` |
| `material.links.plant` | A typed to-one relationship, `ToOne[Plant]` |

Class, field, and link names derive from your KM and its Data Model; the
examples use the Inventory Management KM.

## 1. Register your KM

Register the KM in your application's `pyproject.toml`. No object mapping is
needed:

```toml
[tool.celofast.knowledge-models.inventory]
space-id = "SPACE_ID"
package-id = "PACKAGE_ID"
key = "inventory-km"
mode = "draft"
output = "generated/inventory"
```

### What pull derives from Celonis

| Generated | Derived from |
| --- | --- |
| Object types | Every KM record that reads one Data Model table with a primary key. Event logs and tables without a primary key are skipped. |
| Class names | The table name without its lowercase namespace prefix: `o_celonis_PurchaseDocumentLine` becomes `PurchaseDocumentLine`. |
| Keys | The table's primary key columns (a tuple for composite keys); otherwise the record's declared KM identifier. |
| Field types | Data Model column types for plain columns; the Celonis result schema, then the KM `columnType`, for calculated attributes. |
| Fields | Every attribute with an expression and a known type. Attributes projecting the same expression load once. |
| Links | Each Data Model foreign key between two generated types gives a to-one link on the many side, named after the key column (`Header_ID` becomes `header`), and a to-many link on the one side, named after the plural target class (`purchase_document_lines`). A clashing to-many name gets the column as suffix: `materials_by_origin`. |

Celonis `DATE` columns hold timestamps, so they load as `datetime`. Their
filters also accept a `date`, meaning its midnight:
`PlannedSupply.fields.order_finish_date.gte(date(2026, 9, 23))`.

Pull also test-runs every calculated attribute against a sample of rows
(plain Data Model columns are not probed). Attributes that fail in Celonis, or
return values that do not match their type, are skipped. A failing attribute is
isolated by splitting the query, so one broken formula never hides the others.

Nothing automatic stops a pull. Everything that is not generated is listed with
its reason at the top of the generated `definitions.py`, under
`# Not generated:`, and the command prints a one-line summary.

### Overrides

`mapping` holds optional overrides, inline or as a path to a TOML file relative
to `pyproject.toml`. Record IDs and attribute IDs are the captured KM IDs:

```toml
[tool.celofast.knowledge-models.inventory]
# ...
mapping = "inventory-objects.toml"
```

```toml
# inventory-objects.toml
exclude = ["O_CELONIS_CURRENCYCONVERSION"]   # records not to generate

[objects.O_CELONIS_PLANT]
class = "Site"                               # instead of the derived class name
key = ["ID"]                                 # instead of the primary key
exclude-fields = ["NumberNameConcat"]        # attributes not to load
include-fields = ["NetAmountConverted"]      # keep ${input} placeholders; bind at runtime
types = { OpenedOn = "date" }                # force a type, e.g. a strict date

# Rename an automatic link (same target, cardinality, and columns) ...
[objects.O_CELONIS_PLANT.links.materials]
target = "O_CELONIS_MATERIALMASTERPLANT"
cardinality = "many"
on = { ID = "PLANT_ID" }                     # source attribute ID -> target attribute ID

# ... or add one no foreign key declares (a to-one link joins with LOOKUP).
[objects.O_CELONIS_PURCHASESCHEDULELINE.links.plant]
target = "O_CELONIS_PLANT"
cardinality = "one"
on = { PLANT_ID = "ID" }
```

Only overrides are checked strictly. An override that names an unknown record or
attribute, sets a key that is not a loaded `str`, `int`, `date`, or `datetime`
field, repeats a class name, or declares a to-one link that does not map exactly
the target key raises `ObjectMappingError`, and nothing is written.

Every field is `T | None` except key fields, which are never null. Celofast
never infers a key from a field *name*, and a record's ID is never an instance's
key.

Calculated field types are resolved from the Celonis result schema during pull,
including empty or all-null results when a schema is returned. This schema takes
precedence over missing or incorrect KM `columnType` metadata; explicit `types`
overrides and Data Model column types retain priority. Discovered types are saved
separately from the source definition; offline generation uses that snapshot.

During pull, references to calculated attributes and parameterless KPIs that
depend on KM inputs are expanded locally and their captured defaults are bound
as PQL values. Text
defaults are quoted, including when the source formula omitted quotes. The
generated field uses the same expression that pull validated; the live KM is
never edited. Repull after changing those defaults. Missing defaults are
reported, and `include-fields` retains placeholders for explicit runtime bindings.

A `PU_COUNT` of a source table's single-column primary key can be normalized
through a unique shared child table using `BIND` and `PU_COUNT_DISTINCT`. This
counts each related source object once. Ambiguous paths, filtered counts, and
counts of non-key columns are left unchanged.

Calculated field types are resolved from the Celonis result schema during pull,
including empty or all-null results when a schema is returned. This schema takes
precedence over missing or incorrect KM `columnType` metadata; explicit `types`
overrides and Data Model column types retain priority. Discovered types are saved
separately from the source definition; offline generation uses that snapshot.

During pull, references to calculated attributes and parameterless KPIs that
depend on KM inputs are expanded locally and their captured defaults are bound
as PQL values. Text
defaults are quoted, including when the source formula omitted quotes. The
generated field uses the same expression that pull validated; the live KM is
never edited. Repull after changing those defaults. Missing defaults are
reported, and `include-fields` retains placeholders for explicit runtime bindings.

A `PU_COUNT` of a source table's single-column primary key can be normalized
through a unique shared child table using `BIND` and `PU_COUNT_DISTINCT`. This
counts each related source object once. Ambiguous paths, filtered counts, and
counts of non-key columns are left unchanged.

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
| `objects.py` | Per object type: `PlantDefinition` (typed fields and their expressions), `Plant` (the value class), and `PlantLinks` (its relationships); then the `km` registry. |
| `py.typed` | Marks the package as typed. |

The package is plain Python with no data files. Everything the runtime needs is
written as literals: the KM source, Data Model, and each field's expression and
metadata. The captured KM definition is only the input to generation, so parts
of the KM that no generated type uses (KPIs, filters, excluded records and
fields) are not in the package.

A generated object type looks like this:

```python
class PlantDefinition(_d.ObjectDefinition):
    'Plant'

    _object_type = 'O_CELONIS_PLANT'
    _table = 'o_celonis_Plant'
    _key = ('id',)
    _metadata = {'displayName': 'Plant', 'description': None}

    id: _d.Field[str] = _d.Field('ID', '"o_celonis_Plant"."ID"', 'str')
    country: _d.Field[str | None] = _d.Field('COUNTRY', '"o_celonis_Plant"."Country"', 'str')
    ...


@dataclass(frozen=True, kw_only=True)
class Plant(_o.Object):
    'Plant'

    key: str
    id: str
    country: str | None
    ...

    fields: ClassVar[PlantDefinition] = PlantDefinition()
    relations: ClassVar[type[PlantLinks]]

    @property
    def links(self) -> PlantLinks:
        return PlantLinks(self)


class PlantLinks(_o.Links, source=Plant):
    'Relationships of Plant.'

    materials = _o.ToManyRelation(MaterialMasterPlant, on=(('id', 'plant_id'),), join='fk')
```

Each relationship is declared once. Read from the class
(`Plant.relations.materials`) it builds predicates and aggregates; read from a
loaded object (`plant.links.materials`) it fetches that object's related
objects.

Importing is offline: it does not authenticate, contact Celonis, or import
PyCelonis or pandas. Imports verify the runtime version.

### Definitions

`Plant.fields` describes the type. Iterate it for all fields, or look one up by
its exact captured attribute ID:

```python
Plant.fields.object_type               # "O_CELONIS_PLANT"
Plant.fields.key_fields                # (Plant.fields.id,)
Plant.relations.materials.join        # "fk", "lookup", or None (traversal only)
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
`key_fields` are reserved (some for backward compatibility). An attribute with a reserved or colliding Python
name receives a readable suffix, such as `key_attribute`; each generated field
keeps its attribute ID (`Plant.fields["KEY"]`).

## 3. Retrieve objects

`cf.km(inventory)` validates the Space, Package, lifecycle, KM key, and Data
Model, then returns a `KnowledgeModelClient`. `client.objects(Plant)`
returns an immutable `ObjectCollection[Plant]`.

| Operation | Behavior |
| --- | --- |
| `collection.get(key)` | One object; raises `ObjectNotFoundError` if absent. Composite keys are tuples. |
| `collection.where(*predicates)` | A narrower collection; predicates combine with AND. |
| `collection.order_by(*sorts)` | A reordered collection by fields or relation aggregates: `.asc()`/`.desc()`, or ascending when given plainly. The key breaks ties. |
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
| `f.is_in([x, y])` | PQL `IN`: equal to one of the values; a null never matches. |
| `f.between(low, high)` | PQL `BETWEEN`, both ends inclusive; a null never matches. |
| `f.like("Berlin%")` | PQL `LIKE` on string fields: `%` any text, `_` one character. |
| `a & b`, `a \| b`, `~a` | And, or, and exact complement: `~f.eq(x)` is `f.ne(x)`, including nulls. |
| `Type.relations.one.has(p)` | The related object of a to-one link exists (and matches `p`, if given). |
| `Type.relations.many.any(p)` | At least one related object of a to-many link exists (and matches `p`, if given). |
| `Type.relations.many.count(p)`, `.sum(f, p)`, `.avg(f, p)`, … | An aggregate over related objects that compares and sorts like a field; see below. |

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

### Aggregates over relations

A to-many relation that follows a Data Model foreign key also yields one
aggregate value per object. It compiles to a Pull-Up function on the object's
table, so it can be compared with values, fields of the same type, or other
aggregates, and used in `order_by`:

```python
supplies = MaterialMasterPlant.relations.planned_supplies
firm = PlannedSupply.fields.is_firm_order.eq(1)

short = (
    client.objects(MaterialMasterPlant)
    .where(
        supplies.sum(PlannedSupply.fields.order_quantity, firm)
        .lt(MaterialMasterPlant.fields.safety_stock_quantity)
    )
    .order_by(supplies.count().desc())
    .fetch_page(page_size=50)
)
```

| Aggregate | PQL | Result |
| --- | --- | --- |
| `count(p=None)` | `PU_COUNT` | `int`, 0 without related objects |
| `count_distinct(f, p=None)` | `PU_COUNT_DISTINCT` | `int`, 0 without values |
| `sum(f, p=None)` | `PU_SUM` | the field's numeric type |
| `avg(f, p=None)` | `PU_AVG` | `float` |
| `min(f, p=None)`, `max(f, p=None)` | `PU_MIN`, `PU_MAX` | the field's type |
| `median(f, p=None)` | `PU_MEDIAN` | the field's numeric type; for an even count, the upper middle value |

`p` restricts which related objects count, and may itself use relations.
Aggregates other than the counts are NULL when no related value exists: an
ordering comparison is then false, and `.eq(None)` finds those objects. Null
field values are ignored, as in PQL. Pull-Up functions ignore global filters
and are evaluated per object.

Every read is **one** PQL query, however many relations it nests. Relationship
predicates compile into the same filter:

| Link | PQL |
| --- | --- |
| To-one, following a Data Model foreign key | `BIND(<this table>, <related column>)`, one `BIND` per hop |
| To-one on a plain column without a foreign key | `LOOKUP(<this table>, <related column>, (<this key column>, <related key column>))` |
| To-many, following a foreign key | `PU_COUNT(<this table>, <related key>, <related condition>) > 0` |

`km pull` reads the Data Model's foreign keys and classifies every link. A link
that matches a foreign key in the direction its cardinality implies uses joins
and Pull-Up functions. A single-column to-one link without one uses `LOOKUP`.
Any other link, such as a to-many link with no foreign key, supports
traversal only: `Type.relations.x.any(...)` raises `QueryValidationError`, and
`objects.py` lists the link under "Not generated". A null reference never matches, so
`~relations.x.any(...)` includes objects without related objects.

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
- **No hidden requests.** Reading `plant.country` or `plant.key`, or
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

### Inspect the PQL that runs

PQL is not part of the object API, but every export is logged at DEBUG level on
the `celofast.km` logger:

```python
import logging

logging.basicConfig()
logging.getLogger("celofast.km").setLevel(logging.DEBUG)
```

Each read logs one entry (`Read O_CELONIS_MATERIALMASTERPLANT objects ...`)
with the limit, offset, columns (annotated with field names), filter, and
ordering exactly as sent, including any `BIND`, `LOOKUP`, and `PU_COUNT` a
relationship predicate compiled to. Logs can contain business data such as
keys and filter values; review them before sharing.

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
replace unrelated files or a package pulled from another KM, and verifies the
new package imports before writing it. Restart Python after
pulling so every generated module is reloaded together.

## What this SDK does not do

- No aggregation, grouping, KPI selection, arbitrary PQL filters, or DataFrames.
  Tables configured in a View remain available through
  [Views and inputs](views-and-inputs.md).
- No writes. Future write support will expose explicit supported actions, not a
  generic `save()`.
- No projections or partial objects. Predicates select objects; every read
  still returns complete, typed instances.
