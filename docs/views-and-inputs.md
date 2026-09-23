# Views and inputs

[Documentation](index.md) · [Dictionary queries](dictionary-queries.md)

Use a View when Studio already defines the columns, filters, sorting, or input
controls your application needs. This guide assumes authentication is configured
and uses illustrative View keys and component names.

## Find and execute a table

```python
from celofast import CeloFast

cf = CeloFast("SPACE_ID", "PACKAGE_ID")
view = cf.view("operations-view")

for table in view.tables:
    print(table.id, table.name, table.tab_name)

orders = view.table("Orders")
query_definition = orders.to_query()
frame = orders.execute(limit=100)
```

Views are selected by exact key. Tables are selected by exact component ID
first, then by exact display name. A display name must be unique. If multiple
tables are named `Orders`, select one of the IDs printed above.

`view.tables` includes root table components followed by tables in each tab's
component order. `tab_name` is `None` for a root component.

The query comes from native `Table.get_query()`. It preserves all configured
data-source columns, including ones hidden in the table UI, component filters,
referenced KM filters, and sorting. `to_query()` leaves `${name}` placeholders
intact and does not execute the query or resolve the View's KM for data export.

## Reuse filters from other tables

```python
events = view.table("Events")

query_definition = events.to_query(
    inherit_filters_from=("Orders",),
    extra_filters=('FILTER "Events"."VALID" = 1;',),
)

frame = events.execute(
    inherit_filters_from=("Orders",),
    extra_filters=('FILTER "Events"."VALID" = 1;',),
    limit=100,
)
```

Filter order is: this table's filters, the selected tables' filters in request
order, then `extra_filters`. They combine with AND. The original View remains
unchanged. Inherited selectors use the same ID/unique-name lookup as `table()`.

Use a sequence for `inherit_filters_from` and an iterable for `extra_filters`;
a single bare string is rejected. Table execution also accepts `offset` and
`distinct`, and requests all matching rows when `limit` is omitted.

## View template bindings

```python
view = cf.view("operations-view", variables={"days": "30"})
frame = view.table("Events").execute(variables={"days": "7"}, limit=100)
```

For table execution, binding precedence from lowest to highest is:

1. Defaults in the native View's input-variable definitions.
2. `variables=` passed to `cf.view(...)`.
3. `variables=` passed to `table.execute(...)`.

`view.variables` exposes the first two layers as a read-only mapping. These are
exact string replacements in the exported query, not assignments to control
state or server-managed KM variables. A string literal replacement must include
its PQL quotes. See [raw template bindings](dictionary-queries.md#bind-raw-template-variables).

## Discover supported input controls

```python
input_view = cf.view("input-data")

for control in input_view.controls:
    print(control.id, control.name, control.tab_name, control.variable_keys)
```

| Selector | Collection | `get()` result |
| --- | --- | --- |
| `view.input_box(name_or_id)` | `view.input_boxes` | String or `None`. |
| `view.dropdown(name_or_id)` | `view.dropdowns` | String/`None` for single selection; tuple for multiple selection. |
| `view.selector(name_or_id)` | `view.selectors` | Same selection behavior as dropdowns. |
| `view.date_picker(name_or_id)` | `view.date_pickers` | `datetime.date`, `DateRange`, or `None`. |
| `view.checkbox(name_or_id)` | `view.checkboxes` | `bool` or `None`. |

The collections contain concrete typed handles; `view.controls` combines them.
Selectors use exact component IDs or unique display names. Selecting a control
validates that its binding references declared KM input variables and can
resolve the KM on first use.

### Text and selection controls

```python
search = input_view.input_box("Search")
current_search = search.get()
print(search.placeholder, search.input_type, search.variable_key)

details = search.details()
print(details.value, details.assigned_value, details.default_value)
print(details.uses_default)

groups = input_view.dropdown("Material group")
current_selection = groups.get()
for option in groups.options(limit=100):
    print(option.value, option.label)
```

`get()` returns the effective value. `details()` returns an `InputVariableValue`
containing the assignment, default, effective value, and metadata. Each call
fetches current values from Package Manager for this View and its KM; reading
two controls is not an atomic multi-control snapshot.

`options()` returns a tuple of `DropdownOption` objects from a distinct KM query
over the control's configured data-source attribute and filters. It does not
return the user's current selection. It accepts `limit` and `offset` and omits
null options. Inspect `selection_mode`, `attribute_pql`, `attribute_id`, and
`data_source_id` to understand the configuration.

### Dates and checkboxes

```python
date_control = input_view.date_picker("Planning date")
date_value = date_control.get()

range_control = input_view.date_picker("Planning window")
if range_control.range_selection:
    period = range_control.get()
    print(period.start, period.end)
    print(range_control.start_variable_key, range_control.end_variable_key)

include_closed = input_view.checkbox("Include closed orders").get()
```

Range date pickers use two variable keys. Use `get()` and the start/end
properties for ranges; the single `variable_key` and single-variable
`details()` interface do not represent both values. Dates must be returned as
ISO dates, and checkbox values must decode from `true`/`false`.

## Values and object filters

Reading a control does not automatically filter KM objects. Use the returned
value explicitly when that is the intended application behavior:

```python
# client = cf.km(inventory); Plant is a generated value class.
country = input_view.input_box("Country").get()

plants = client.objects(Plant)
if country:
    plants = plants.where(Plant.fields.country.eq(country))
page = plants.fetch_page(page_size=100)
```

These control handles expose reads and inspection; Celofast does not expose a
`set()` method for them. Defaults captured during `celofast km pull`, View
template defaults, and current Package Manager values are separate. Choose
the source your application needs explicitly.

## Native access and errors

- `view.native` gives the native View; `view.content` gives parsed View content.
- `view.km` lazily resolves a `KnowledgeModelConnection` exposing `native`,
  `data_model`, and `augmentation_tables`; it has no query methods.
- `table.component` and `control.component` expose native components.
- `control.settings` exposes a read-only mapping of serialized settings.
- `view.input_definitions` exposes the KM input definitions; first access may
  resolve the KM and fetch metadata.

Missing or ambiguous components raise `TableNotFoundError`,
`AmbiguousTableError`, `ComponentNotFoundError`, or `AmbiguousComponentError`.
Invalid variable bindings raise `ComponentVariableError`. Malformed or absent
value responses raise `ResourceResolutionError`. See
[Troubleshooting](troubleshooting.md) for diagnosis.
