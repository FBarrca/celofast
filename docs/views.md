# Views

[Documentation](index.md) · [Getting started](getting-started.md) · [API reference](api-reference.md)

A Studio View already defines tables (their columns, filters, and sorting) and
input fields such as dropdowns and date pickers. Celofast lets you read both
from Python:

```python
from celofast import CeloFast

cf = CeloFast("SPACE_ID", "PACKAGE_ID")
view = cf.view("operations-view")

orders = view["Orders"].rows(limit=100)      # a pandas DataFrame
region = view["Region"].value                # the dropdown's current value
```

Use a View when Studio already defines the tabular result you need. To load
business objects by key and follow their relationships, use
[Knowledge Models](knowledge-model-sdk.md) instead.

## Contents

1. [Open a View](#1-open-a-view)
2. [Read a table](#2-read-a-table)
3. [Narrow a table](#3-narrow-a-table)
4. [Read an input field](#4-read-an-input-field)
5. [List dropdown options](#5-list-dropdown-options)
6. [Input values in tables](#6-input-values-in-tables)
7. [Export a table's query](#7-export-a-tables-query)
8. [Errors](#8-errors)

## 1. Open a View

Select the View by its exact key, not its display name:

```python
view = cf.view("operations-view")
```

`view[...]` returns one table or input field, by its component ID or its
display name:

```python
orders = view["Orders"]              # by display name
orders = view["table-orders"]        # by component ID
```

List everything the View contains, root components first, then each tab:

```python
for element in view.elements:
    print(element.id, element.name, element.tab_name, type(element).__name__)
```

A display name shared by two elements (for example, the same table in two
tabs) raises `AmbiguousComponentError`, which lists the component IDs; use one
of those instead.

`cf.view()` reads the View's definition once and caches it per key. Data is
only read when you ask for rows or values.

## 2. Read a table

```python
orders = view["Orders"]
frame = orders.rows()                             # every row
first_page = orders.rows(limit=100)               # the first 100 rows
second_page = orders.rows(limit=100, offset=100)
unique = orders.rows(distinct=True)
```

`rows()` runs the table exactly as configured in Studio, including columns
hidden in the UI, its filters, and its sorting, and returns a pandas
`DataFrame` with one column per table column. Every call reads fresh data.

## 3. Narrow a table

Add filters for one read, without changing the View:

```python
events = view["Events"]

frame = events.rows(
    inherit_filters_from=["Orders"],                  # also apply the Orders table's filters
    extra_filters=['FILTER "Events"."VALID" = 1;'],  # complete PQL filter statements
    limit=100,
)
```

Filters combine with AND, in this order: the table's own filters, those of the
tables named in `inherit_filters_from`, then `extra_filters`. Name tables by
display name or component ID. Pass lists, not single strings.

## 4. Read an input field

`.value` reads the field's current value from Celonis and returns it as a
Python value:

```python
search = view["Search"].value                 # input box: str or None
region = view["Region"].value                 # dropdown: str or None
groups = view["Material groups"].value        # multi-select: a tuple
due = view["Due date"].value                  # date picker: datetime.date or None
period = view["Planning window"].value        # range date picker: DateRange(start, end)
include_closed = view["Include closed"].value # checkbox: bool or None
```

| Field | `.value` |
| --- | --- |
| Input box | `str` or `None` |
| Dropdown, selector | `str` or `None`; a `tuple` when several values can be selected |
| Date picker | `datetime.date` or `None`; a range gives `DateRange(start, end)` |
| Checkbox | `bool` or `None` |

Each read asks Celonis again, so a change in Studio shows up on the next read.
Store the value if you need it to stay the same. Inputs are read-only.

**Details.** `.details()` returns the whole record of the field's input
variable, including whether a value is assigned or the default applies:

```python
details = view["Region"].details()
print(details.value)            # the effective value (a string)
print(details.assigned_value)   # None when the default applies
print(details.default_value)
print(details.uses_default)
print(details.display_name, details.data_type, details.scope)
```

For a range date picker, `.details()` returns `DateRangeDetails(start, end)`,
one record per end, read together.

**Whose value?** An input variable with the user-specific scope
(`USER_SPECIFIC`) holds a separate value for each user. Celofast reads the
value of the user it's authenticated as, which for an OAuth application is not
the person looking at the View in the browser, and it can't read another
user's value. For your application to see what people select in the View, make
the input variable global in Studio (scope `SYSTEM`): everyone then shares one
value.

## 5. List dropdown options

```python
for option in view["Region"].options(limit=100):
    print(option.value, option.label)
```

For a dropdown or selector backed by a KM attribute, `options()` returns the
attribute's distinct values, with the dropdown's configured filters. For a
dropdown with items entered in Studio, it returns those items. Both accept
`limit` and `offset`.

## 6. Input values in tables

A table's filters and columns often use input variables, written `${name}` in
PQL. `rows()` fills them in with the inputs' current values, the same ones
`.value` returns, so the rows match what the View shows for those inputs.

To see a table for another selection, change the input in Studio (or have the
user change it); the next `rows()` call uses the new value. An input with
neither a value nor a default raises `UnresolvedVariableError` before the query
runs.

## 7. Export a table's query

`to_query()` returns the table's query as a plain dictionary of PQL strings,
without running it. It accepts the same `inherit_filters_from` and
`extra_filters` as `rows()`:

```python
query = view["Orders"].to_query(extra_filters=['FILTER "Plant"."Country" = \'DE\';'])
```

```python
{
    "columns": {"Case ID": '"Orders"."ID"', "Value": 'KPI("order_value")'},
    "filters": ["FILTER @active_orders;", 'FILTER "Plant"."Country" = \'DE\';'],
    "order_by": [{"pql": 'KPI("order_value")', "ascending": False}],
}
```

The dictionary contains only strings, so you can save it as JSON or YAML. KPI
and KM filter references (`FILTER @active_orders;`) and `${name}` input
placeholders are kept as they are.

## 8. Errors

| Error | Meaning |
| --- | --- |
| `ComponentNotFoundError` | No table or input has that ID or display name. List `view.elements`. |
| `AmbiguousComponentError` | Several elements share the display name; use a component ID. |
| `TableNotFoundError`, `AmbiguousTableError` | The same, for a table named in `inherit_filters_from`. |
| `ComponentVariableError` | The input field isn't bound to an input variable the KM or View defines. |
| `UnresolvedVariableError` | A table uses an input that has no value or default. |
| `ResourceResolutionError` | Celonis returned no value, or an unreadable one, for an input. |

Errors from running the query in Celonis are raised unchanged. For native
access, `view.native` is the PyCelonis View, `view.km` its Knowledge Model, and
each element's `.component` its PyCelonis component. See also
[Troubleshooting](troubleshooting.md#views-and-controls).
