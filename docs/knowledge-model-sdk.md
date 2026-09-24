# Knowledge Models

[Documentation](index.md) · [Getting started](getting-started.md) · [API reference](api-reference.md)

Celofast turns a Celonis Knowledge Model (KM) into a Python package of typed
classes, one per business object, and lets you query them:

```python
from celofast import CeloFast
from generated.inventory import MaterialMasterPlant, Plant, km as inventory

client = CeloFast("SPACE_ID", "PACKAGE_ID").km(inventory)

plant = client.objects(Plant).get("SAP_ECC::100::1000")
print(plant.plant_name, plant.country)

german_plants = client.objects(Plant).where(Plant.fields.country.eq("DE")).fetch_page()
materials = plant.links.materials.fetch_page()          # this plant's MaterialMasterPlants
```

Your editor autocompletes every class, field, and relationship, and a type
checker verifies them. The examples on this page use the Inventory Management
KM; your names come from your own KM.

## Contents

1. [Generate the package](#1-generate-the-package)
2. [Load objects](#2-load-objects)
3. [Filter](#3-filter)
4. [Sort](#4-sort)
5. [Follow relationships](#5-follow-relationships)
6. [Filter and sort by related objects](#6-filter-and-sort-by-related-objects)
7. [KM input variables](#7-km-input-variables)
8. [Keep the package up to date](#8-keep-the-package-up-to-date)
9. [Customize what is generated](#9-customize-what-is-generated)
10. [See the PQL that runs](#10-see-the-pql-that-runs)

## 1. Generate the package

Register the KM in your application's `pyproject.toml`. Use its exact key, not
its display name:

```toml
[tool.celofast.knowledge-models.inventory]
space-id = "SPACE_ID"
package-id = "PACKAGE_ID"
key = "inventory-km"
mode = "draft"                 # or "published"
output = "generated/inventory"
```

Then pull it:

```bash
uv run celofast km pull inventory
```

Pull reads the KM and its Data Model and writes a plain Python package to
`output`:

- **One class per object.** Every KM record that reads a Data Model table with
  a primary key becomes a class, named after the table:
  `o_celonis_MaterialMasterPlant` becomes `MaterialMasterPlant`.
- **One field per attribute.** Names are snake_case (`IsDiscontinued` becomes
  `is_discontinued`). Types come from the Data Model, or, for calculated
  attributes, from running them in Celonis.
- **Relationships from foreign keys.** Each Data Model foreign key gives both
  directions: a purchase document line's `header` (to-one, named after the
  `Header_ID` column) and a purchase document's `purchase_document_lines`
  (to-many).

Pull also test-runs every calculated attribute. Anything it can't generate,
such as an event log, a record without a primary key, or a formula that fails
in Celonis, is skipped rather than failing the pull. Each skipped item is
listed with its reason at the top of the generated `objects.py`, under
`# Not generated:`.

Import the package like any module. Importing is offline: it doesn't connect
to Celonis.

```python
from generated.inventory import Plant, km as inventory
```

`km` (imported here as `inventory`) is the package's registry. Pass it to
`cf.km()` to get a client:

```python
from celofast import CeloFast

cf = CeloFast("SPACE_ID", "PACKAGE_ID")
client = cf.km(inventory)
```

`cf.km()` checks that the package was pulled from the same Space, Package,
lifecycle, and Data Model you are connected to.

## 2. Load objects

`client.objects(Plant)` is the collection of all plants. Nothing is fetched
until you ask for objects:

```python
plants = client.objects(Plant)

plant = plants.get("SAP_ECC::100::1000")      # one object by key
page = plants.fetch_page(page_size=100)       # the first 100, in key order
```

Iterate a page, and fetch the next one while `has_more` is true:

```python
page = plants.fetch_page(page_size=100)
while page is not None:
    for plant in page:
        print(plant.key, plant.country)
    page = page.next_page()                  # None after the last page
```

`page_size` is 1 to 10,000. Pages are offsets over live data, so a change in
Celonis between two fetches can move an object between pages.

**Keys.** `plant.key` is the object's business key. Types with a composite key
take a tuple, in the order of `Plant.fields.key_fields`:

```python
# A type keyed by plant and day:
line = client.objects(StockLine).get(("PLANT-1", datetime(2024, 1, 31)))
```

`get()` raises `ObjectNotFoundError` when no object has that key.

**Loaded objects.** Every object is a frozen dataclass holding every field, as
plain Python values (`str`, `int`, `float`, `bool`, `date`, `datetime`). Every
field can be `None` except key fields. Reading a value never contacts Celonis;
only `get()`, `fetch_page()`, `next_page()`, and `fetch()` on a to-one
relationship do.

## 3. Filter

Build conditions from the class's `fields` and pass them to `where()`:

```python
german = client.objects(Plant).where(Plant.fields.country.eq("DE"))
```

`Plant.fields.country` is the field's definition, used in conditions;
`plant.country` is a loaded value.

| Condition | Matches |
| --- | --- |
| `f.eq(x)`, `f.ne(x)` | Equal / not equal. `f.eq(None)` finds nulls. |
| `f.lt(x)`, `f.lte(x)`, `f.gt(x)`, `f.gte(x)` | Less / greater than. Never matches a null. |
| `f.is_in(["DE", "FR"])` | One of the values. |
| `f.between(low, high)` | Between two values, both included. |
| `f.like("Berlin%")` | Text pattern: `%` is any text, `_` one character. |
| `f.lt(other_field)` | A comparison with another field of the same object. |

Values are checked against the field's type when you build the condition, so
`Plant.fields.country.eq(1)` fails immediately. Date fields also accept a
`date`, which means that day's midnight.

Combine conditions with `&` (and), `|` (or), and `~` (not). Several arguments
to `where()`, or chained `where()` calls, also combine with and:

```python
stock = MaterialMasterPlant.fields

at_risk = client.objects(MaterialMasterPlant).where(
    stock.is_discontinued.eq(0)
    & stock.current_valuated_stock_quantity.lt(stock.safety_stock_quantity)
    & ~stock.abc_classification.eq("C")
)
```

Use `&`, `|`, and `~`, not Python's `and`, `or`, and `not`, which raise an
error. `~` is an exact opposite: `~f.eq(x)` also matches objects where `f` is
null.

Conditions are plain values, so you can name and reuse business rules:

```python
active = stock.is_discontinued.eq(0)
below_safety_stock = stock.current_valuated_stock_quantity.lt(stock.safety_stock_quantity)

client.objects(MaterialMasterPlant).where(active & below_safety_stock).fetch_page()
```

## 4. Sort

```python
client.objects(PurchaseScheduleLine).order_by(
    PurchaseScheduleLine.fields.expected_delivery_date.asc(),
    PurchaseScheduleLine.fields.expected_quantity.desc(),
).fetch_page()
```

A field given without `.asc()` or `.desc()` sorts ascending. Ties are always
broken by the key, so paging is stable. Without `order_by()`, objects come in
key order.

## 5. Follow relationships

`links` on a loaded object reaches its related objects:

```python
plant = client.objects(Plant).get("SAP_ECC::100::1000")

materials = plant.links.materials                 # a collection of MaterialMasterPlant
purchased = materials.where(MaterialMasterPlant.fields.procurement_type.eq("F"))
page = purchased.fetch_page(page_size=50)

home = page.items[0].links.plant.fetch()          # to-one: Plant or None
```

A to-many relationship is an ordinary collection: filter, sort, `get()`, and
page it as above. A to-one relationship has `fetch()`, which returns the
related object or `None`. If the object's reference is null, you get an empty
result without a request.

## 6. Filter and sort by related objects

`relations` on the class builds conditions on related objects. The whole
condition runs as one query in Celonis.

**A related object matches**: `has()` for to-one, `any()` for to-many:

```python
supply = PlannedSupply.fields

client.objects(MaterialMasterPlant).where(
    MaterialMasterPlant.relations.plant.has(Plant.fields.country.eq("DE"))
    & ~MaterialMasterPlant.relations.planned_supplies.any(
        supply.is_firm_order.eq(1) & supply.order_quantity.gt(0)
    )
)
```

Without an argument, `has()` and `any()` mean "a related object exists".
Conditions nest, so a rule on one type can reuse a rule on another:

```python
external_purchase = PurchaseDocument.fields.is_canceled.eq(0) & (
    PurchaseDocument.relations.vendor.has(Vendor.fields.is_internal_vendor.eq(0))
)
active_external_line = PurchaseDocumentLine.fields.is_canceled.eq(0) & (
    PurchaseDocumentLine.relations.header.has(external_purchase)
)
```

**Aggregates over a to-many relationship** give one value per object. Compare
and sort them like fields:

```python
supplies = MaterialMasterPlant.relations.planned_supplies
firm = PlannedSupply.fields.is_firm_order.eq(1)

(
    client.objects(MaterialMasterPlant)
    .where(
        supplies.sum(PlannedSupply.fields.order_quantity, firm)
        .lt(MaterialMasterPlant.fields.safety_stock_quantity)
    )
    .order_by(supplies.count().desc())
    .fetch_page()
)
```

| Aggregate | Value |
| --- | --- |
| `count(condition=None)` | Number of related objects; 0 if there are none. |
| `count_distinct(field, condition=None)` | Number of distinct values; 0 if there are none. |
| `sum(field, ...)`, `avg(field, ...)`, `median(field, ...)` | Of a numeric field. |
| `min(field, ...)`, `max(field, ...)` | Smallest / largest value. |

The optional condition limits which related objects count. Every aggregate
except the two counts is `None` when there is no related value, and
`.eq(None)` finds those objects.

Relationships are filterable when they follow a Data Model foreign key, or are
to-one links on a single column (joined by value). Other relationships, such
as a declared to-many link without a foreign key, can be followed with `links`
but not used in conditions; their `relations` raise `QueryValidationError`.

## 7. KM input variables

Attributes that use KM input variables (`${name}`) are generated like any
other. Each read uses the input's current value in the KM (the assigned value,
otherwise its default), so a change in Studio takes effect on the next read,
without a pull.

`inventory.variables` lists the inputs the package uses. If an input has
neither a value nor a default, reading a field that uses it raises
`UnresolvedVariableError`: set a value in Studio, or
[exclude the field](#9-customize-what-is-generated).

## 8. Keep the package up to date

Pull again after the KM or its Data Model changes, then restart Python:

```bash
uv run celofast km pull inventory
```

In CI, check that the package matches the KM without writing anything:

```bash
uv run celofast km pull inventory --check
```

`--check` prints a diff of every generated file that would change. It exits
**0** when up to date, **1** when the package is out of date, and **2** on an
error. Changes to parts of the KM the package doesn't use, such as KPIs or
filters, don't count.

Don't edit generated files; pull replaces them. Keep your own code outside the
output directory: pull refuses to write into a directory with files it didn't
generate.

## 9. Customize what is generated

Pull needs no configuration beyond section 1. To change its choices, add a
`mapping`: inline, or as a TOML file next to `pyproject.toml`:

```toml
[tool.celofast.knowledge-models.inventory]
# ...
mapping = "inventory-objects.toml"
```

Records and attributes are named by their KM IDs, as shown in Studio:

```toml
# inventory-objects.toml

# Don't generate these records.
exclude = ["O_CELONIS_CURRENCYCONVERSION"]

[objects.O_CELONIS_PLANT]
class = "Site"                          # rename the class
key = ["ID"]                            # choose the key (default: the primary key)
exclude-fields = ["NumberNameConcat"]   # don't load these attributes
types = { OpenedOn = "date" }           # force a type
```

`types` accepts `str`, `int`, `float`, `bool`, `date`, and `datetime`. Celonis
dates load as `datetime`; use `"date"` for a plain date.

**Relationships.** Declaring a link with the same target and columns as an
automatic one renames it. Declaring any other link adds it:

```toml
# Rename Plant.material_master_plants to Plant.materials.
[objects.O_CELONIS_PLANT.links.materials]
target = "O_CELONIS_MATERIALMASTERPLANT"
cardinality = "many"
on = { ID = "PLANT_ID" }                # this record's attribute -> target attribute

# Add a link that no foreign key declares.
[objects.O_CELONIS_PURCHASESCHEDULELINE.links.plant]
target = "O_CELONIS_PLANT"
cardinality = "one"                     # a to-one link must map the target's key
on = { PLANT_ID = "ID" }
```

A mistake in the mapping, such as an unknown record or attribute, or a key or
link that doesn't fit, raises `ObjectMappingError` and nothing is written.

Pass a different mapping file for one pull with `--mapping`. See the
[command reference](api-reference.md#km-command-line) for all options.

## 10. See the PQL that runs

Each read is one query. To see it exactly as sent, enable DEBUG logging for
`celofast.km`:

```python
import logging

logging.basicConfig()
logging.getLogger("celofast.km").setLevel(logging.DEBUG)
```

Logs contain filter values and keys, which can be business data.

## What this is not for

The KM API loads whole business objects. It has no column selection, grouping,
KPIs, raw PQL, DataFrames, or writes. For anything
else, `client.native` and `client.data_model` are the underlying PyCelonis
objects.

Something not working? See [Troubleshooting](troubleshooting.md#generating-object-packages).
