# Celonis PQL: Process functions — offline context

## About this document

This file consolidates the Celonis Product Documentation section **PQL Function Library → Process**, including the Process landing page, its 24 direct function pages, and all 13 function pages under the **Process Index** and **Process Reference** subcategories. It is written to remain useful without opening the source pages. It paraphrases and condenses the documentation; the exact source links are deliberately omitted.

The documentation pages showed **Last modified: 2026-04-16** when collected in the browser on **2026-09-23**. Function grammar below is copied in substance and normalized for readability; some pages contain additional examples and advanced grammar that are not reproduced verbatim.

## 1. Shared model and working assumptions

Process functions operate on an event log and calculate with its case identifier and activity column. The Case-Id is determined by the Data Model editor. Most process functions let a query choose an activity column; the chosen column can also be transformed before it is passed to the function.

A useful preprocessing operation is `REMAP_VALUES`:

```pql
-- Map two activity labels to the same label
REMAP_VALUES("Table1".ACTIVITY, ['B', 'BC'], ['C', 'BC'])

-- Hide activity B by mapping it to NULL
REMAP_VALUES("Table1".ACTIVITY, ['B', NULL])
```

For the documentation's sample case `A, B, C`, the first transformation produces `A, BC, BC`; the second produces `A, NULL, C`. This can be used to normalize an event log before applying process calculations.

### Temporary output and grain

- Activity-level indices and lag/lead results are temporary columns associated with an activity table.
- Case-level summaries and match/conformance results are generally returned at case grain, even when calculated from activity rows.
- Check each function's result grain before combining its result with other columns or filters.
- Several functions ignore NULL activities; some preserve NULL rows as NULL, while range functions may treat a NULL row inside the selected range differently. Those distinctions are called out below.

## 2. Quick reference by task

| Task | Starting point | Notes |
|---|---|---|
| Normalize, combine, or hide activity labels | `REMAP_VALUES` | Transform the activity column before the process calculation. |
| Read an earlier or later activity value | `ACTIVITY_LAG` / `ACTIVITY_LEAD` | Offset counts non-NULL values; default is 1. |
| Number activity types or positions | `INDEX_ACTIVITY_TYPE`, `INDEX_ACTIVITY_ORDER` | `ACTIVATION_COUNT` and `PROCESS_ORDER` are deprecated in favor of these. |
| Count consecutive repeats | `INDEX_ACTIVITY_LOOP` | Reverse counterpart is available. |
| Select a range of events | `CALC_CROP` / `CALC_CROP_TO_NULL` | One returns a 1/NULL mask; the other retains the original values inside the range. |
| Count activities or measure elapsed time | `CALC_REWORK` / `CALC_THROUGHPUT` | Both yield case-level values. |
| Describe cases by activity sequence | `VARIANT` | `SHORTENED` caps consecutive self-loop length. |
| Find cases with activities, sequences, or patterns | `MATCH_ACTIVITIES`, `PROCESS EQUALS`, `MATCH_PROCESS`, `MATCH_PROCESS_REGEX` | Choose based on whether order matters and how expressive the pattern must be. |
| Check a process model | `BPMN_CONFORMS` / `CONFORMANCE` | Binary BPMN fit vs. activity-level Petri-net violations. |
| Cluster similar variants | `CLUSTER_VARIANTS` | Expensive; has distinct-variant and execution-time limits. |
| Build a multi-object event log | `CREATE_EVENTLOG` | `PROJECT_ON_OBJECT` is a deprecated alias. |
| Combine existing activity streams | `MERGE_EVENTLOG` / `MERGE_EVENTLOG_DISTINCT` | Target case set comes from the first input; duplicate handling differs. |
| Reference configured data-model columns | `ACTIVITY_COLUMN`, `CASE_ID_COLUMN`, etc. | Avoid hard-coding physical table and column names. |

## 3. Ordering, occurrence, and neighbor functions

### `ACTIVITY_LAG`

Returns a prior value from the same case; the result is a temporary activity-table column.

```pql
ACTIVITY_LAG(activity_table.column [, offset])
```

- `activity_table.column`: column on an activity table.
- `offset`: number of non-NULL values preceding the current row in that column; defaults to `1`.
- NULL handling: the documentation says the lagging value for a NULL value is the same as the lagging value for the next non-NULL value; offsets count only non-NULL values.
- Use it for predecessor activity comparisons, sequence calculations, and ping-pong patterns.

### `ACTIVITY_LEAD`

Returns a following value from the same case; the result is a temporary activity-table column.

```pql
ACTIVITY_LEAD(activity_table.column [, offset])
```

- `activity_table.column`: column on an activity table.
- `offset`: number of non-NULL values following the current row; defaults to `1`.
- NULL handling: offsets count only non-NULL values. For a NULL value, the documented leading-value behavior follows the last non-NULL value; a final row without a following value returns NULL.
- Use it for successor activity comparisons and sequence calculations.

### `INDEX_ACTIVITY_ORDER`

Returns the forward position of each non-NULL activity within a case.

```pql
INDEX_ACTIVITY_ORDER(activity_table.column)
```

The result is a temporary activity-table column. NULL input rows stay NULL and do not affect positions.

### `INDEX_ACTIVITY_ORDER_REVERSE`

Returns the reverse position of each non-NULL activity within a case.

```pql
INDEX_ACTIVITY_ORDER_REVERSE(activity_table.column)
```

NULL input rows stay NULL and do not affect positions. The result is temporary and activity-based.

### `INDEX_ACTIVITY_TYPE`

Returns the occurrence count for each activity type as the case advances. For example, the first occurrence of an activity type is numbered 1, its next occurrence 2, and so on.

```pql
INDEX_ACTIVITY_TYPE(activity_table.column)
```

The result is a temporary integer column on the activity table. NULLs are ignored; a column consisting only of NULLs yields only NULLs. For parallel activities the absolute order is based on timestamps. This is the recommended replacement for deprecated `ACTIVATION_COUNT`.

### `INDEX_ACTIVITY_TYPE_REVERSE`

Returns the occurrence count for each activity type when scanning a case in reverse, from the end toward the beginning.

```pql
INDEX_ACTIVITY_TYPE_REVERSE(activity_table.column)
```

The result is a temporary integer activity-table column. For parallel activities the reverse absolute order is timestamp-based.

### `INDEX_ACTIVITY_LOOP`

Counts consecutive repetitions of the same activity within each case. The count restarts when the activity changes.

```pql
INDEX_ACTIVITY_LOOP(activity_table.column)
```

The result is activity-based. NULL rows remain NULL and are ignored. When events are parallel, the absolute order used for counting is based on timestamps.

### `INDEX_ACTIVITY_LOOP_REVERSE`

The reverse-order version of `INDEX_ACTIVITY_LOOP`.

```pql
INDEX_ACTIVITY_LOOP_REVERSE(activity_table.column)
```

NULL rows remain NULL and are ignored; parallel activity order uses timestamps in reverse.

### Deprecated: `ACTIVATION_COUNT`

This operator returns the number of times an activity has already occurred at each point in each case.

```pql
ACTIVATION_COUNT(activity_table.column)
```

The output is an occurrence counter per activity row. For parallel activities, the absolute order is timestamp-based. NULLs are ignored; when all values are NULL, the result is all NULL. **Use `INDEX_ACTIVITY_TYPE` for new queries.**

### Deprecated: `PROCESS_ORDER`

Returns the position of each non-NULL activity within a case.

```pql
PROCESS_ORDER(activity_table.column)
```

Only non-NULL activities are counted. **Use `INDEX_ACTIVITY_ORDER` for new queries.**

## 4. Event-range and case-level calculations

### `CALC_CROP`

Selects a range of events within each case and marks in-range activities with `1`; out-of-range values become NULL.

```pql
CALC_CROP(begin_event TO end_event, activity_table.string_column)
```

Each boundary can be one of:

- `CASE_START` or `CASE_END`
- `FIRST_OCCURRENCE[activity_name]`
- `LAST_OCCURRENCE[activity_name]`

The input is usually the activity column. The result is an activity-based integer mask. NULLs outside the range remain NULL; NULL rows that fall inside the range are marked `1`.

Example: `CALC_CROP(FIRST_OCCURRENCE['B'] TO LAST_OCCURRENCE['C'], "Table1"."activity")` marks the rows from the first B through the last C in each case.

### `CALC_CROP_TO_NULL`

Selects the same kinds of event ranges but retains each original activity value inside the range and sets values outside it to NULL.

```pql
CALC_CROP_TO_NULL(begin_event TO end_event, activity_table.string_column)
```

Boundary grammar is the same as `CALC_CROP`. The result is a temporary activity-table column. NULL rows inside the range remain NULL; they are not converted to an activity or to a 1. Use this when downstream calculations need the retained activity labels rather than a boolean mask.

### `CALC_REWORK`

Counts activity rows per case and returns a temporary case-level column.

```pql
CALC_REWORK()
CALC_REWORK(filter_condition)
CALC_REWORK(activity_table.column)
CALC_REWORK(filter_condition, activity_table.column)
```

- `filter_condition`: only activities matching the condition are counted.
- `activity_table.column`: optionally identifies which event log to use in a model with multiple logs.
- NULL activity values are not relevant to the count; the calculation counts how often a Case-Id appears. Cases without a join partner in the case table are ignored. A NULL Case-Id present in the case table is represented with result 0 because NULL cases do not join.

### `CALC_THROUGHPUT`

Returns elapsed time for each case between two event-range boundaries. Output is a temporary case-table column.

```pql
CALC_THROUGHPUT(begin_event TO end_event, timestamps [, activity_table.string_column])
```

- `timestamps`: integer-valued activity-table column, often made by converting a timestamp column.
- Optional activity column: string column from the same activity table; it determines which activities the event-range specifiers refer to. If omitted, the activity column for that table is used.
- Boundaries use `CASE_START`, `CASE_END`, `FIRST_OCCURRENCE[activity_name]`, or `LAST_OCCURRENCE[activity_name]`.
- If the end activity occurs before the start activity, the result is NULL. A one-activity case also yields NULL. An unknown activity name in a boundary generates a warning and NULL result.

### `SOURCE` and `TARGET`

These operators align values from different activity rows onto one row, making expressions such as timestamp differences possible.

```pql
SOURCE(activity_table.column [, activity_table.filter_column]
       [, edge_configuration [WITH START([start_value])]])

SOURCE(activity_table.column [, activity_table.filter_column],
       WITH START([start_value]))

TARGET(activity_table.column [, activity_table.filter_column]
       [, edge_configuration [WITH END([end_value])]])

TARGET(activity_table.column [, activity_table.filter_column],
       WITH END([end_value]))
```

- The first column is the value to project; optional `filter_column` and edge configuration control which source or target event is selected.
- `SOURCE` may define a start value; `TARGET` may define an end value.
- NULL values in the projected activity column remain NULL in the output. Rows whose filter-column value is NULL are ignored.
- Typical purpose: retrieve a preceding/following event's timestamp or attribute and compare it to the current row. Edge options determine the event relation, so consult the relevant model/query grammar when constructing non-default edges.

## 5. Variants, activity matching, and model conformance

### `VARIANT` and `SHORTENED`

Aggregates the activity sequence of a case into a string describing the process variant.

```pql
VARIANT(activity_table.string_column)
SHORTENED(VARIANT(activity_table.column) [, max_cycle_length])
```

`VARIANT` returns one case-based value per case. NULL activity inputs are ignored. `SHORTENED` reduces a run of more than `max_cycle_length` consecutive repetitions of the same activity to that many repetitions; default maximum is 2.

### `MATCH_ACTIVITIES`

Flags cases based on activity membership and optional start/end constraints, without requiring a full ordered path.

```pql
MATCH_ACTIVITIES(
  [activity_table.string_column,]
  [STARTING activity_list]
  [, NODE activity_list]
  [, NODE_ANY activity_list]
  [, ENDING activity_list]
  [, EXCLUDING activity_list]
  [, EXCLUDING_ALL activity_list]
)
```

`activity_table.string_column` defaults to the activity column of the default event log. An activity list is a bracketed comma-separated list of activity names.

- `STARTING`: the case starts with one of the listed activities.
- `NODE`: the case contains all listed activities; their exact order is not the matching criterion.
- `NODE_ANY`: the case contains at least one listed activity.
- `ENDING`: the case ends with one of the listed activities.
- `EXCLUDING`: the case contains none of the listed activities and has at least one non-NULL activity.
- `EXCLUDING_ALL`: the case does not contain all listed activities and has at least one non-NULL activity.

Returns a case-level integer flag: 1 for a match and 0 otherwise. NULL activity values do not influence the flag. For ordered patterns, use `MATCH_PROCESS` or `MATCH_PROCESS_REGEX` instead.

### `PROCESS EQUALS`

A compact expression language for matching a process variant. It is simpler and less powerful than `MATCH_PROCESS` and `MATCH_PROCESS_REGEX`.

```text
PROCESS [ON activity_table.string_column] [NOT] EQUALS
       [START] activity (TO activity)* [END]
```

- If no column is supplied, the default activity column is used.
- `START` / `^` anchors the pattern at the beginning; `END` / `$` anchors it at the end.
- `TO` / `->` connects successive activities; `ANY` / `*` can stand for any activity.
- An activity can be a literal name, `LIKE` plus a wildcard pattern (case-sensitive), or a parenthesized group of acceptable activity names.
- A nonexistent activity name raises a warning. Then `PROCESS EQUALS` matches nothing and `PROCESS NOT EQUALS` matches everything. Empty cases (no activities or only NULL activities) match `PROCESS NOT EQUALS`.
- Returns a case-level match condition that can be used in a filter or other condition.

### `MATCH_PROCESS`

Matches case variants against a graph-like pattern of named nodes and edges.

```text
MATCH_PROCESS(
  [activity_table.string_column,]
  node (, node)* CONNECTED BY edge (, edge)*
)
```

- The activity column defaults to the default event log's activity column.
- A node has a type such as `NODE`, `OPTIONAL`, `LOOP`, `OPTIONAL_LOOP`, `STARTING`, or `ENDING`, followed by one or more acceptable activities and an `AS node_name` identifier.
- A single activity may be a literal or `LIKE` wildcard pattern. `LIKE` is case-sensitive. Nodes can contain multiple alternatives.
- Edges connect named nodes and are marked `DIRECT` or `EVENTUALLY`; direct requires a direct succession, while eventually permits intervening activities.
- Returns a temporary case-level integer column: 1 for matching cases, 0 otherwise. Often used in a filter.

### `MATCH_PROCESS_REGEX`

Matches variants using a regular expression defined over the activity sequence.

```pql
MATCH_PROCESS_REGEX(activity_table.string_column, regular_expression)
```

The result is a temporary case-level integer column: 1 if the variant matches and 0 if it does not. The regular-expression grammar supports:

- A quoted activity name.
- `LIKE 'wildcard pattern'` for activity names with wildcards.
- `>>` for sequence/concatenation and `|` for alternation.
- `^` and `$` anchors for beginning and end of the variant.
- Bracketed activity-name lists, optionally negated with `!`.
- Parenthesized expressions and repetition operators `+`, `?`, `*`, and `{from[,to]}`.
- `AS alias` for naming subexpressions in comma-separated regular-expression components.

An activity name absent from the model produces a warning. Some queries can be CPU-intensive; execution exceeding 10 minutes is stopped and reported.

### `BPMN_CONFORMS`

Performs a binary yes/no check of traces against a BPMN model.

```text
BPMN_CONFORMS(
  flattened_events_table.column,
  bpmn_model,
  [ALLOW(filter_or_shorthand [, ...])]
)
```

Input is a column from a flattened event table. The result is a case-level integer column: 0 when a case has any deviation, 1 when the full case conforms. Use it to filter deviating cases or average the flags for a conformance rate.

The BPMN model is encoded as `[vertices], [edges]`:

- A vertex is identified by a unique integer ID and a type: `BPMN_START`, `BPMN_END`, `BPMN_EXCLUSIVE_CHOICE`, `BPMN_PARALLEL`, or a task written `[vertex_id BPMN_TASK 'task_name']`.
- A model has exactly one start vertex and one end vertex.
- A task name must correspond to an activity name in the flattened event table and must not be NULL.
- An edge is a pair `[start_vertex end_vertex]`; vertices are identified by their IDs.

### `CONFORMANCE` and `READABLE`

Checks event activities against a Petri-net process model using token replay with backtracking and error repair.

```text
CONFORMANCE(
  activity_table.string_column,
  [places], [transitions], [edges], [mapping], [start_places], [end_places]
)
READABLE(conformance_query)
```

Model parts are lists: unique place IDs; unique transition IDs; flow edges between places and transitions; activity-name-to-transition pairs; start-place IDs; and end-place IDs. `READABLE` turns the conformance query's violation flags into English descriptions. A query can be written to a variable or sourced from the Analysis conformance-checker sheet. NULL activity values conform with any Petri net. The operator flags activity-level deviations. The docs warn that some computations exceed 10 minutes and are stopped.

## 6. Variant clustering

### `CLUSTER_VARIANTS`

Groups similar process variants (traces) into clusters.

```text
CLUSTER_VARIANTS(variant_column, MIN_PTS, EPSILON)
```

- `variant_column`: column containing variants.
- `MIN_PTS`: minimum density of similar variants needed to form a cluster. Lower values tend to create more clusters; higher values tend to classify more variants as noise. `ESTIMATE_CLUSTER_PARAMS` can estimate this value.
- `EPSILON`: search radius, measured by the number of different relations between successive activities. Must be an integer from 0 through 5. The docs recommend a low value such as 2; 0 requires variants to be equal, and higher values make it more likely that variants fall into the same cluster.
- Output is case-based. Cluster IDs identify assigned clusters; `-1` means noise; `-2` means an empty case with no activities.
- Expensive in memory and CPU. Limited to 10,000,000 distinct variants. An execution exceeding 10 minutes is stopped.

### `ESTIMATE_CLUSTER_PARAMS`

Estimates candidate `MIN_PTS` values for `CLUSTER_VARIANTS`.

```text
ESTIMATE_CLUSTER_PARAMS(table.variant_column, epsilon, number_of_values, recursion_depth)
```

- `epsilon`: same search-radius concept and integer range 0–5 as `CLUSTER_VARIANTS`.
- `number_of_values`: number of candidate values to estimate per recursion; must be at least 1.
- `recursion_depth`: maximum number of estimation recursions; must be at least 1.
- Produces an integer column of estimated `MIN_PTS` values, with at most `number_of_values * recursion_depth` entries.
- Expensive and potentially disruptive to analysis responsiveness; limited to 100,000 distinct variants. The documentation notes the estimates can materially affect the clustering result.

## 7. Constructing and combining event logs

### `CREATE_EVENTLOG`

Creates an activity table projected onto a chosen lead object and selected event types. It supports object-centric data models.

```text
CREATE_EVENTLOG(
  object_table_name [FILTER lead_object_filter],
  INCLUDE
    included_event_1 [VIA (relationship_1)] [FILTER event_filter_1],
    included_event_2 [VIA (relationship_2)] [FILTER event_filter_2],
    ...
).column_name
```

- `object_table_name`: lead object, whose rows define the case perspective.
- `lead_object_filter`: optional filter on the lead object; its common table may be a different table if connected in the data model.
- `included_event_i`: event table to include.
- `VIA (relationship_i)`: optional per-event override for the projection path.
- `event_filter_i`: optional filter for that event table.
- Access output with `TABLE.COLUMN` syntax. `LEAD_OBJECT_ID`, `ACTIVITY`, and `TIMESTAMP` are generated by default; other included-event attributes are generated lazily when requested.
- For each event table, the operator chooses a path minimizing traversed objects; a direct object-event path is preferred over a path through another object. Equal-length paths are chosen deterministically.
- Events are merged and deduplicated so each event instance appears at most once per case. The result is joined to the lead object and can be used like a classical event log for PQL calculations. Within a case, rows sort by timestamp and, when specified, the sorting column.

### Deprecated alias: `PROJECT_ON_OBJECT`

`PROJECT_ON_OBJECT` is a deprecated alias for `CREATE_EVENTLOG`; use `CREATE_EVENTLOG` for new queries. It requires an OCPM data model. Its projection concepts, event selection, filters, relationship override, generated columns, and path selection match the event-log projection behavior described above.

```text
PROJECT_ON_OBJECT(
  object_table_name [FILTER lead_object_filter],
  INCLUDE
    included_event_1 [VIA (relationship_1)] [FILTER event_filter_1],
    included_event_2 [VIA (relationship_2)] [FILTER event_filter_2],
    ...
).column_name
```

### `MERGE_EVENTLOG` and `MERGE_EVENTLOG_DISTINCT`

Merges two same-type columns from activity tables whose case tables are connected in the data model.

```text
MERGE_EVENTLOG(
  target_table.column [, FILTER target_table_filter_expression],
  source_table.column [, FILTER source_table_filter_expression]
)

MERGE_EVENTLOG_DISTINCT(
  target_table.column [, FILTER target_table_filter_expression],
  source_table.column [, FILTER source_table_filter_expression]
)
```

The first input is the target; the second is merged into corresponding target cases. Only cases present in the target column's case table appear in the result. The resulting internal table is joined to the first input's case table. Rows sort by timestamp and, if specified, sorting column. The two operators differ only in duplicate handling: ordinary `MERGE_EVENTLOG` may contain duplicate activities; `MERGE_EVENTLOG_DISTINCT` removes them.

NULL and join behavior: cases with no corresponding case-table entry are ignored; a NULL source case ID does not remove the target case; rows with NULL case ID, timestamp, or activity value are ignored. The docs discourage `MERGE_EVENTLOG` in object-centric data models and recommend the alternative named in that operator's documentation.

### `EVENTLOG_SOURCE_TABLE`

Returns the source activity-table name for each row of a dynamically created event log.

```pql
EVENTLOG_SOURCE_TABLE(dynamically_created_eventlog.column)
```

The input is a column from a generated log, such as one returned by `MERGE_EVENTLOG` or `CREATE_EVENTLOG`.

### `DEFAULT ACTIVITY_COLUMN`

Temporarily overrides which activity column is treated as the default for one query.

```text
DEFAULT ACTIVITY_COLUMN activity_table.column;
```

The specified value must be a string column of an activity table. Operators that would use the default event log's activity column use this column during the query.

### `TRANSIT_COLUMN`

Computes transition edges between related cases from two different processes. The two activity tables need to be linked in the Data Model. The miner describes the interaction to identify.

```text
TRANSIT_COLUMN(
  TIMESTAMP_INTERLEAVED_MINER(table_a.activity_column, table_b.activity_column),
  activity_column
)

TRANSIT_COLUMN(
  TIMESTAMP_NONINTERLEAVED_MINER(table_a.activity_column, table_b.activity_column),
  activity_column
)

TRANSIT_COLUMN(
  MATCH_MINER(table_a.activity_column, table_b.activity_column,
              table_a.out_msg, table_b.in_msg),
  activity_column
)

TRANSIT_COLUMN(
  MANUAL_MINER(table_a.activity_column, table_b.activity_column,
               [manual_value_1, manual_value_2], ...),
  activity_column
)
```

The final `activity_column` belongs to either input activity table. The four miner families cover timestamp-interleaved events, timestamp-noninterleaved events, matching output/input message values, or explicitly supplied manual value pairs.

## 8. Activity and case table references

The Process Reference functions avoid hard-coding the physical names of configured event-log tables and standard columns. Most column-reference functions accept an optional `expression`:

```text
REFERENCE_FUNCTION([expression])
```

- When the expression contains a column from an activity table, the corresponding configured table or column is selected.
- When no expression is given, the default activity table or its configured column is used.
- A table reference may also be passed where supported. Table-returning functions can be used anywhere a table name is accepted.
- These are useful with multiple activity/case tables and event logs assembled from other tables.

### `ACTIVITY_TABLE(expression)`

Returns a reference to the activity table connected to the supplied activity-table column; with no argument, returns the default activity table.

### `CASE_TABLE(expression)`

Returns a reference to the case table connected to the supplied activity-table column; with no argument, returns the default case table.

### `ACTIVITY_COLUMN([expression])`

Returns the configured activity column of the activity table identified by the expression, or of the default activity table when omitted. A table reference selects that table's activity column.

### `CASE_ID_COLUMN([expression])`

Returns the configured case column for the activity table identified by the expression, or the default activity table when omitted. A table reference selects that table's case column.

### `TIMESTAMP_COLUMN([expression])`

Returns the configured timestamp column for the selected activity table. With no expression, uses the default activity table; a table reference may select a particular activity table.

### `END_TIMESTAMP_COLUMN([expression])`

Returns the configured end-timestamp column. If no end-timestamp column is defined for the selected activity table, it returns that table's timestamp column.

### `SORTING_COLUMN([expression])`

Returns the configured sorting column for the selected activity table, or for the default activity table when no expression is supplied.

## 9. Complete child-page inventory

The following inventory preserves the Process section's child-page coverage represented above.

**Process category (24 direct function pages):** `ACTIVATION_COUNT`; `ACTIVITY_LAG`; `ACTIVITY_LEAD`; `BPMN_CONFORMS`; `CALC_CROP`; `CALC_CROP_TO_NULL`; `CLUSTER_VARIANTS`; `CONFORMANCE`; `CREATE_EVENTLOG`; `DEFAULT ACTIVITY_COLUMN`; `SOURCE` / `TARGET`; `ESTIMATE_CLUSTER_PARAMS`; `EVENTLOG_SOURCE_TABLE`; `MATCH_ACTIVITIES`; `MERGE_EVENTLOG` / `MERGE_EVENTLOG_DISTINCT`; `PROCESS EQUALS`; `MATCH_PROCESS_REGEX`; `MATCH_PROCESS`; `PROCESS_ORDER`; `PROJECT_ON_OBJECT`; `CALC_REWORK`; `CALC_THROUGHPUT`; `TRANSIT_COLUMN`; `VARIANT`.

**Process Index subcategory:** `INDEX_ACTIVITY_LOOP`; `INDEX_ACTIVITY_LOOP_REVERSE`; `INDEX_ACTIVITY_ORDER`; `INDEX_ACTIVITY_ORDER_REVERSE`; `INDEX_ACTIVITY_TYPE`; `INDEX_ACTIVITY_TYPE_REVERSE`.

**Process Reference subcategory:** `ACTIVITY_COLUMN`; `ACTIVITY_TABLE`; `CASE_ID_COLUMN`; `CASE_TABLE`; `END_TIMESTAMP_COLUMN`; `SORTING_COLUMN`; `TIMESTAMP_COLUMN`.

## 10. Short reminders

- Deprecated replacements: `ACTIVATION_COUNT` → `INDEX_ACTIVITY_TYPE`; `PROCESS_ORDER` → `INDEX_ACTIVITY_ORDER`; `PROJECT_ON_OBJECT` → `CREATE_EVENTLOG`.
- `CALC_CROP` outputs a 1/NULL mask; `CALC_CROP_TO_NULL` retains activity values in the range.
- `MATCH_ACTIVITIES` ignores exact ordering; choose `MATCH_PROCESS`, `MATCH_PROCESS_REGEX`, or `PROCESS EQUALS` when sequence matters.
- `BPMN_CONFORMS` is case-level binary conformance; `CONFORMANCE` gives activity-level Petri-net conformance information.
- `VARIANT` ignores NULLs. Index-order functions keep NULL rows NULL and do not count them. Check each function's NULL behavior before interpreting results.
- Variant clustering, process regex matching, and Petri-net conformance may be expensive; the documented 10-minute execution cutoff applies to the noted operators.

