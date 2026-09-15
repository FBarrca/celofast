# PDR: Celofast Knowledge Model SDK

- **Status:** Draft
- **Product:** Celofast
- **Target:** Celofast 0.x
- **Audience:** Celofast maintainers and Python developers building on Celonis
- **Last updated:** 2026-09-15

## 1. Executive summary

Celofast should generate a typed, read-only Python SDK from a Celonis Knowledge
Model (KM) hosted in the cloud.

The generated SDK represents KM records, attributes, identifiers, KPIs,
filters, variables, and other supported KM items as first-class Python
objects. Each object preserves its KM identity, documentation, type
information, relationships, and executable definition. Developers can explore
the KM in their IDE and pass the same objects to Celofast features without
copying IDs or writing PQL.

The product workflow is:

```text
Cloud Knowledge Model
        │
        │ celofast km pull
        ▼
Generated, typed Python KM SDK
        │
        ├── application code
        ├── Celofast queries
        ├── View and input bindings
        ├── validation and CI
        ├── documentation and discovery
        └── future Celofast capabilities
```

The generated object graph is the product. Querying is one consumer of that
object graph, not its organizing abstraction.

Celonis remains the only source of truth. `celofast km pull` is a one-way
operation. Celofast does not create, update, migrate, or delete Knowledge Model
items.

## 2. Product thesis

Knowledge Models already define a semantic contract for an application, but
Python code currently experiences that contract as dynamic metadata and
strings. This prevents static discovery, encourages duplicated constants, and
delays incompatibility detection until runtime.

Celofast should turn the remote semantic contract into a local developer
contract:

- A KM record becomes a typed Python `Record` object.
- A record attribute becomes an `Attribute[T]`.
- A KPI becomes a `KPI[T]` or `KPI[Any]` when its value type is unknown.
- A KM filter becomes a `Filter`.
- A KM variable becomes a `Variable[T]`.
- Descriptions become IDE documentation.
- KM PQL becomes immutable internal behavior carried by the relevant object.

Application code then depends on stable Python symbols rather than manually
repeating KM IDs and expressions.

The closest established product analogy is Palantir Foundry's Ontology SDK
(OSDK): centrally managed semantic objects are exposed to application
developers as generated, strongly typed SDK objects. Drizzle's generated
schema objects are a useful secondary analogy, but Celofast is not primarily a
database ORM or query builder.

## 3. Problem statement

Celofast currently relies on dynamic PyCelonis content objects and
string-based query definitions. For example:

```python
query = {
    "columns": {
        "Plant": (
            '"o_celonis_Plant"."PlantNumber" || \' - \' || '
            '"o_celonis_Plant"."PlantName"'
        ),
    },
}
```

This creates several problems:

1. Developers must inspect Studio or raw KM content to discover available
   objects.
2. IDs and PQL are copied into application code without static validation.
3. IDEs cannot autocomplete the contents of a particular KM.
4. Descriptions, types, sources, and validation state are separated from the
   expressions that use them.
5. A KM change is normally discovered only when application code executes.
6. Different Celofast features develop separate ways to refer to the same KM
   item.

A generated SDK gives Celofast and its consumers one canonical local object
model for the remote KM.

## 4. Goals

### 4.1 Product goals

- Make a Celonis KM directly discoverable through Python autocomplete.
- Generate the complete effective KM; users do not configure a subset.
- Make KM objects reusable first-class values across Celofast.
- Provide type hints derived from authoritative KM metadata.
- Remove the need for application developers to author or copy PQL for
  generated KM objects.
- Make cloud KM changes visible through deterministic generated-code diffs.
- Detect stale or incompatible local KM SDKs in CI.
- Preserve a clear one-way ownership model from Celonis to generated code.

### 4.2 Technical goals

- Pull effective KM content through the existing PyCelonis integration.
- Represent every object returned by the effective KM, including inherited and
  auto-generated content.
- Generate importable Python code with explicit, statically discoverable
  members.
- Preserve source IDs, descriptions, types, PQL, origins, validation state,
  and parent-child relationships.
- Provide a small stable runtime protocol for generated KM objects.
- Produce byte-identical output when the source KM is unchanged.
- Support both draft and published KM lifecycle modes.
- Keep importing the generated package completely offline.
- Remain backward compatible with existing Celofast APIs.

## 5. Non-goals

The initial product will not:

- Edit, create, delete, migrate, or deploy KM objects.
- Provide a `push` operation.
- Treat generated Python as the source of truth for the KM.
- Require developers to write PQL.
- Parse or rewrite PQL to infer business meaning.
- Be centered on a new query-builder API.
- Model KM records as database tables or provide CRUD semantics.
- Generate data rows or materialize KM records during import.
- Generate only an application-selected subset of the KM.
- Guarantee a precise type when the KM does not provide authoritative type
  metadata.
- Replace the native PyCelonis escape hatches already exposed by Celofast.

## 6. Product analogy: Palantir Ontology SDK

Palantir's Ontology SDK generates types and functions from the portion of a
centrally managed Ontology relevant to an application. It enables developers
to explore Ontology objects in their editor while the Ontology remains
centrally maintained.

Celofast should apply the same pattern to Celonis Knowledge Models:

| Palantir Foundry | Celofast |
| --- | --- |
| Ontology | Knowledge Model |
| Object type | Record |
| Property | Attribute |
| Action | KM action |
| Generated OSDK | Generated Celofast KM SDK |
| Central Ontology maintenance | Cloud KM remains authoritative |
| Generated type safety | `Record`, `Attribute[T]`, `KPI[T]`, and related types |

The initial Celofast scope is narrower. Palantir's SDK includes reads, searches,
links, actions, and writeback. Celofast initially generates a read-only local
representation of the KM and lets existing or future Celofast capabilities
consume it.

Unlike Palantir's application-specific subset generation, one Celofast SDK
represents the complete effective KM. Consumers choose which generated objects
to use, but generation itself is never filtered.

Reference: [Palantir Ontology SDK overview][palantir-osdk].

## 7. User experience

### 7.1 Configure a KM SDK

Projects may configure one or more KMs in `pyproject.toml`:

```toml
[tool.celofast.knowledge-models.inventory]
space-id = "SPACE_ID"
package-id = "PACKAGE_ID"
key = "inventory-km"
mode = "draft"
output = "generated_km/inventory"
```

Authentication continues to use Celofast's existing client and environment
configuration. Credentials are never written to the generated package.

Explicit CLI arguments should also be supported for scripts and initial use:

```bash
celofast km pull \
  --space-id "$CELONIS_SPACE_ID" \
  --package-id "$CELONIS_PACKAGE_ID" \
  --km inventory-km \
  --mode draft \
  --output generated_km/inventory
```

### 7.2 Pull the SDK

```bash
celofast km pull inventory
```

The command:

1. Authenticates using the existing Celofast configuration.
2. Resolves the requested draft or published KM.
3. Retrieves the effective final KM content.
4. Normalizes supported items into a versioned internal representation.
5. Generates a typed Python package.
6. Validates that every generated Python file compiles.
7. Atomically replaces the previous generated package.

If any step fails, the previous valid generated package remains untouched.

### 7.3 Import and explore KM objects

```python
from generated_km.inventory import inventory_km

plant = inventory_km.records.o_celonis_plant
attribute = plant.attributes.number_name_concat

attribute.id
# "NumberNameConcat"

attribute.display_name
# "Plant No. & Name"

attribute.description
# "Plant a material is stored at, produced at, or shipped to."

attribute.column_type
# "string"

attribute.source
# AttributeSource.KNOWLEDGE_MODEL

attribute.validation.status_type
# ValidationStatusType.OPEN
```

The IDE knows that `attribute` is an `Attribute[str]`. It can autocomplete both
the KM hierarchy and the common runtime metadata API.

### 7.4 Refresh after a KM change

When the cloud KM changes:

```bash
celofast km pull inventory
```

The regenerated source produces a normal Git diff:

- New object: a Python member is added.
- Removed object: a Python member is removed.
- Renamed ID: represented as a removal and addition.
- Changed `columnType`: the generic Python type changes.
- Changed PQL: the object's internal expression changes.
- Changed display name or description: generated documentation changes.

Celofast never guesses migrations or silently redirects a removed object to a
similarly named replacement.

## 8. Canonical example

Given this KM content:

```yaml
- id: O_CELONIS_PLANT
  attributes:
    - id: NumberNameConcat
      displayName: Plant No. & Name
      description: Plant a material is stored at, produced at, or shipped to.
      pql: |
        "o_celonis_Plant"."PlantNumber" || ' - ' || "o_celonis_Plant"."PlantName"
      columnType: string
      type: ATTRIBUTE
      attributeSource: KNOWLEDGE_MODEL
      validationStatus:
      validationStatusType: OPEN
    - id: NumberFormatted
      displayName: Plant No.
      description: Plant a material is stored at, produced at, or shipped to.
      pql: |
        "o_celonis_Plant"."PlantNumber"
      columnType: string
      type: ATTRIBUTE
      attributeSource: KNOWLEDGE_MODEL
      validationStatus:
      validationStatusType: OPEN
  newAttributes: []
  augmentedAttributes: []
  flags: []
  priorities: []
  triggers: []
  businessRules: []
  type: RECORD
  origin: PACKAGE
```

Celofast generates the conceptual equivalent of:

```python
# Generated by `celofast km pull`. Do not edit.
from typing import ClassVar

from celofast.sdk import (
    Attribute,
    AttributeSource,
    AttributeNamespace,
    KnowledgeModel,
    Record,
    RecordNamespace,
    ValidationStatus,
    ValidationStatusType,
)
from celofast.pql import Expression


class OCelonisPlantAttributes(AttributeNamespace):
    number_name_concat: ClassVar[Attribute[str]] = Attribute(
        id="NumberNameConcat",
        display_name="Plant No. & Name",
        description=(
            "Plant a material is stored at, produced at, or shipped to."
        ),
        expression=Expression(
            '"o_celonis_Plant"."PlantNumber" || \' - \' || '
            '"o_celonis_Plant"."PlantName"'
        ),
        column_type="string",
        source=AttributeSource.KNOWLEDGE_MODEL,
        validation=ValidationStatus(
            status_type=ValidationStatusType.OPEN,
        ),
    )

    number_formatted: ClassVar[Attribute[str]] = Attribute(
        id="NumberFormatted",
        display_name="Plant No.",
        description=(
            "Plant a material is stored at, produced at, or shipped to."
        ),
        expression=Expression('"o_celonis_Plant"."PlantNumber"'),
        column_type="string",
        source=AttributeSource.KNOWLEDGE_MODEL,
        validation=ValidationStatus(
            status_type=ValidationStatusType.OPEN,
        ),
    )


class OCelonisPlant(Record):
    id: ClassVar[str] = "O_CELONIS_PLANT"
    origin: ClassVar[str] = "PACKAGE"
    attributes: ClassVar[OCelonisPlantAttributes] = OCelonisPlantAttributes()


class InventoryRecords(RecordNamespace):
    o_celonis_plant: ClassVar[OCelonisPlant] = OCelonisPlant()


inventory_km = KnowledgeModel(
    key="inventory-km",
    mode="draft",
    records=InventoryRecords(),
)
```

The exact generated syntax may evolve, but this object hierarchy is required:

```python
inventory_km.records.o_celonis_plant
inventory_km.records.o_celonis_plant.attributes.number_name_concat
inventory_km.records.o_celonis_plant.attributes.number_formatted
```

## 9. Full Knowledge Model scope

Every pull generates the complete effective KM. There is no include list,
exclude list, application-specific subset, or lazy remote lookup.

The generated root must represent every object returned by the KM, including:

- Knowledge Model identity and lifecycle metadata
- Records and identifiers
- Attributes, new attributes, and augmented attributes
- KPIs, parameters, targets, aggregations, and breakdowns
- Filters and variables
- Activities and actions
- Anomalies and event logs
- Custom objects
- Flags, priorities, triggers, and business rules
- Inherited and auto-generated items

Celofast can introduce richer category-specific behavior incrementally, but it
cannot omit an item merely because no specialized runtime class exists yet. An
unsupported category is generated as an immutable `GenericKnowledgeObject`
that preserves its ID, category, hierarchy, and complete normalized metadata.

If an item cannot be represented without losing its identity or content, pull
fails with its full KM path. Silent omission is never allowed.

This completeness invariant can be tested by comparing the object counts and
source IDs in the normalized KM response with those in the generated manifest.

## 10. Runtime object contract

Generated code depends on a small, manually maintained runtime in Celofast.
The runtime defines behavior shared by every generated SDK.

### 10.1 Common metadata

All generated items should expose a consistent read-only interface where the
source provides the value:

```python
item.id
item.display_name
item.short_display_name
item.description
item.scope
item.internal_note
item.auto_generated
item.type
item.origin
item.custom_attributes
```

Category-specific objects add fields such as `column_type`, `unit`, `format`,
`source`, `validation`, and `filter_ids`.

### 10.2 Object hierarchy

The SDK should model KM ownership explicitly:

```text
KnowledgeModel
├── records
│   └── Record
│       ├── identifier
│       ├── attributes
│       ├── new_attributes
│       ├── augmented_attributes
│       ├── flags
│       ├── priorities
│       ├── triggers
│       └── business_rules
├── kpis
├── filters
├── variables
├── activities
├── actions
├── anomalies
├── event_logs
└── custom_objects
```

Every category returned by the effective KM must be present in this hierarchy,
using a specialized runtime type where available and
`GenericKnowledgeObject` otherwise.

### 10.3 Immutability

Generated objects are immutable value objects. They expose no mutation,
`save`, `update`, `delete`, or `push` operations. This makes their relationship
to the cloud KM unambiguous and prevents accidental local divergence.

### 10.4 Object identity

Every generated item has a stable identity composed from:

```text
KM key + lifecycle mode + category path + source ID
```

Python names are ergonomic access paths; source IDs remain the authoritative
identity and are always retained.

## 11. PQL handling

PQL belongs to the generated KM object, not to normal application code.

For an attribute, the SDK should retain the exact expression returned by the
KM and expose it through a read-only Celofast expression abstraction:

```python
attribute.expression  # Expression[str]
attribute.pql         # exact source string, for inspection/debugging
```

The generator must preserve PQL verbatim. The first release does not parse, optimize,
normalize, or reformat it.

When a Celofast capability needs an executable expression, the object converts
it to the appropriate native SaolaPy type internally:

```python
column = attribute.to_pql_column(alias="Plant")
```

Application developers may inspect `.pql`, but they do not need to construct
or modify it.

KPIs and filters should preserve native KM reference semantics rather than
blindly expanding their definitions into every consumer. Their exact execution
adapter must be confirmed during the metadata spike.

## 12. Type generation

Attribute `columnType` maps conservatively to Python generics:

| KM type family | Generated type |
| --- | --- |
| string/text | `Attribute[str]` |
| boolean | `Attribute[bool]` |
| integer | `Attribute[int]` |
| decimal/float/number | `Attribute[float]` |
| date | `Attribute[datetime.date]` |
| datetime/timestamp | `Attribute[datetime.datetime]` |
| unknown, absent, or unsupported | `Attribute[Any]` |

The exact mapping table must be based on observed and documented KM values.
The generator emits `Any` plus a warning instead of guessing.

Current metadata may not reliably describe KPI, identifier, or variable value
types. Those objects default to `Any` unless an authoritative type is present.
Celofast must not parse arbitrary PQL to manufacture a type.

KM metadata does not consistently describe result nullability. The first release must
not claim a non-null runtime result solely from `columnType`.

## 13. Python naming

Generated access names derive from KM IDs, not display names.

The generator must:

1. Convert member names to valid `snake_case`.
2. Convert record/type names to valid `PascalCase`.
3. Prefix identifiers that begin with a digit.
4. Suffix Python keywords with `_`.
5. Resolve normalized-name collisions deterministically.
6. Preserve the exact source ID on every object.

Example:

| KM ID | Python symbol |
| --- | --- |
| `O_CELONIS_PLANT` | `OCelonisPlant` / `o_celonis_plant` |
| `NumberNameConcat` | `number_name_concat` |
| `NumberFormatted` | `number_formatted` |
| `class` | `class_` |

Display-name changes update documentation but do not change the Python access
path. ID changes are breaking changes and are represented as removal plus
addition.

## 14. Generated package layout

One configured KM produces one Python package:

```text
generated_km/inventory/
├── __init__.py
├── records.py
├── objects.py
├── schema.py
├── schema.json
└── py.typed
```

- `records.py` contains record namespaces, identifiers, and attributes.
- `objects.py` contains top-level KPIs, filters, variables, and other supported
  KM objects.
- `schema.py` assembles the root `KnowledgeModel` object.
- `schema.json` contains the source identity, normalized metadata fingerprint,
  generator version, and Python-name mapping.
- `py.typed` marks the generated package as typed.

Generated files contain a prominent do-not-edit header. Hand-written
application extensions and compositions live outside this directory.

Generation must be deterministic: pulling an unchanged KM twice produces
byte-identical files. Volatile timestamps must not appear in generated output.

## 15. Pull, check, and lifecycle behavior

### 15.1 Pull

`celofast km pull` is the primary command because data flows in one direction.
The command replaces only the configured generated package.

The term `sync` should not be used because it implies bidirectional
reconciliation. No `push` command should exist.

### 15.2 Check

CI can verify that checked-in generated code matches the remote KM:

```bash
celofast km pull inventory --check
```

`--check` pulls and normalizes in memory, reports object-level differences,
does not modify files, and exits non-zero when the generated SDK is stale.

Example:

```text
inventory-km changed:
  + records.O_CELONIS_PLANT.attributes.StorageLocation
  ~ records.O_CELONIS_PLANT.attributes.NumberFormatted.columnType
  - filters.LegacyPlantFilter
```

### 15.3 Draft and published modes

Draft and published KMs are distinct source contracts. The selected mode is
recorded in the generated SDK and manifest.

A project may generate both modes into different packages. Celofast must not
silently fall back from one mode to the other.

## 16. Downstream capabilities

The same generated object should be usable throughout Celofast.

### 16.1 Query integration

Existing query dictionaries can accept generated expression objects:

```python
plant = inventory_km.records.o_celonis_plant

query = {
    "columns": {
        "Plant": plant.attributes.number_name_concat,
        "Plant Number": plant.attributes.number_formatted,
    },
}

result = cf.km(inventory_km.key).execute(query)
```

Celofast unwraps the objects into native PQL internally. A richer typed query
builder may be added later, but it is not required to deliver the KM SDK.

### 16.2 View and input integration

View dropdowns, selectors, and other components can expose their bound KM
attribute as a generated `Attribute[T]` when the component and SDK refer to the
same KM identity. This gives View code the same object vocabulary as direct KM
code.

### 16.3 Application schemas and ML features

Applications can use generated objects as stable feature definitions and
input/output metadata:

```python
FEATURES = (
    plant.attributes.number_name_concat,
    inventory_km.kpis.inventory_value,
)
```

### 16.4 Documentation and tooling

Generated docstrings and metadata can power IDE discovery, documentation,
schema browsers, validation tools, and future editor integrations without
introducing a second KM parser.

## 17. Architecture

```text
KnowledgeModelHandle
        │
        ▼
PyCelonis final content adapter
        │
        ▼
Versioned normalized KM model
        │
        ├──► deterministic Python generator
        ├──► schema.json + fingerprint
        └──► object-level change report

Generated Python SDK
        │
        ▼
Celofast KM object runtime
        │
        ├──► query execution
        ├──► View bindings
        ├──► validation
        └──► application tooling
```

### 17.1 PyCelonis adapter

- Reads `FinalKnowledgeModelContent` through the resolved native KM.
- Handles optional collections and version differences in one place.
- Includes all inherited and auto-generated items that are part of the
  effective KM.
- Does not parse Studio YAML when resolved metadata is available.

### 17.2 Normalized model

- Uses Celofast-owned Pydantic models rather than serializing PyCelonis
  transport classes directly.
- Preserves source metadata required for code generation and change reporting.
- Sorts collections by stable source IDs.
- Carries an explicit format version.

### 17.3 Generator

- Renders explicit Python members for static analyzers.
- Escapes PQL and documentation safely.
- Validates generated modules using Python compilation before installation.
- Writes to a temporary directory and replaces output atomically.

### 17.4 Runtime

- Defines stable immutable classes such as `KnowledgeModel`, `Record`,
  `Attribute[T]`, `KPI[T]`, `Filter`, and `Variable[T]`.
- Keeps generated packages small and consistent.
- Adapts executable objects to SaolaPy only when a consumer requires it.

## 18. Compatibility

The feature is additive:

- Existing string-based `QueryDefinition` values continue to work.
- Existing View table behavior remains unchanged.
- Generated attributes may be accepted anywhere Celofast currently accepts a
  query expression, after explicit normalization.
- Native PyCelonis objects remain accessible through current escape hatches.

Generated SDKs declare the minimum compatible Celofast runtime and schema
format versions. Importing with an incompatible runtime raises a focused error
that instructs the user to upgrade Celofast or rerun `km pull`.

## 19. Error handling

The implementation should distinguish:

- **Pull errors:** authentication, permissions, KM resolution, and upstream
  PyCelonis failures.
- **Source schema errors:** duplicate IDs, invalid parent-child relationships,
  or required metadata missing from the KM response.
- **Generation errors:** invalid output paths, name collisions that cannot be
  resolved, unsafe literals, or compilation failures.
- **Runtime compatibility errors:** generated SDK and installed Celofast
  versions are incompatible.
- **Consumer errors:** a generated object is used with a different KM or in an
  unsupported capability.

Errors identify the full source path, for example:

```text
inventory-km.records.O_CELONIS_PLANT.attributes.NumberFormatted
```

Warnings are emitted for recoverable loss of precision, such as an unknown
`columnType` mapped to `Any` or an item emitted as
`GenericKnowledgeObject`. The generated manifest still contains every source
item.

## 20. Security and governance

Generated SDKs contain KM metadata and PQL. They may expose internal Data Model
names and business logic and must follow the repository controls of the
consuming application.

The generator must never persist:

- OAuth credentials or tokens
- Tenant base URLs unless explicitly requested as non-secret metadata
- Raw HTTP headers
- Unrelated package or tenant metadata
- Data returned by executing KM expressions

Importing a generated SDK is offline and cannot bypass Celonis authorization.
Any operation that reads actual data continues to use the caller's Celonis
credentials and platform permissions.

## 21. Testing requirements

### 21.1 Introspection and normalization

- Parse representative draft and published final KM content.
- Preserve source IDs, PQL, types, descriptions, origins, and validation state.
- Handle empty and missing optional collections.
- Preserve parent-child relationships.
- Produce a stable fingerprint independent of source collection order.

### 21.2 Code generation

- The provided `O_CELONIS_PLANT` example generates a record with two
  discoverable `Attribute[str]` members.
- Generated modules compile and import on every supported Python version.
- Pyright or mypy resolves generated attribute types correctly.
- PQL containing quotes, newlines, Unicode, and backslashes is escaped safely.
- Python keywords, digits, Unicode IDs, and normalized-name collisions are
  handled deterministically.
- Repeated pulls from unchanged content produce byte-identical output.
- A failed pull leaves the previous valid package untouched.

### 21.3 Object runtime

- Generated objects are immutable.
- Common metadata fields behave consistently across categories.
- Exact source IDs remain available regardless of generated Python names.
- `Attribute[T]` converts to the equivalent native `PQLColumn`.
- Objects reject use with a mismatched KM identity when a consumer requires
  that validation.

### 21.4 Change detection

- Additions and removals produce an object-level diff.
- PQL-only changes update the internal expression.
- `columnType` changes update the generic type.
- Documentation-only changes are classified separately.
- `--check` detects stale generated output without writing files.

## 22. Acceptance criteria

The first release is complete when:

1. `celofast km pull` generates an importable Python SDK from a cloud KM.
2. The generated SDK represents every object in the effective KM; source and
   generated manifests have matching object IDs and counts.
3. The provided plant record generates `number_name_concat` and
   `number_formatted` as `Attribute[str]`.
4. Specialized and generic generated objects preserve the KM's IDs,
   descriptions, type metadata, PQL, source, origin, validation state, and
   parent-child relationships where present.
5. Importing and inspecting the SDK requires no Celonis connection.
6. Generated objects are immutable and expose no KM mutation operations.
7. A generated attribute can be consumed by the existing Celofast KM query
   execution path without user-authored PQL.
8. Re-pulling a changed KM deterministically updates the generated SDK.
9. `celofast km pull --check` detects stale generated code in CI.
10. Existing Celofast APIs remain backward compatible.

## 23. Delivery plan

### Phase 0: Metadata compatibility spike

- Capture sanitized KM fixtures, including the provided plant record.
- Confirm actual KM `columnType` values.
- Verify effective content in draft and published modes.
- Inventory every collection and nested item returned by representative KMs.
- Confirm native expression behavior for attributes, KPIs, and filters.

### Phase 1: KM object runtime

- Implement immutable common metadata and namespace types.
- Implement `KnowledgeModel`, `Record`, `Attribute[T]`, `KPI[T]`, `Filter`, and
  `Variable[T]`.
- Implement `GenericKnowledgeObject` so all remaining KM items have a lossless
  generated representation.
- Add expression adapters required by existing Celofast consumers.

### Phase 2: Pull and code generation

- Add the versioned normalized KM model.
- Implement PyCelonis-to-Celofast adapters.
- Implement deterministic Python generation and atomic output replacement.
- Add `celofast km pull` and project configuration.
- Add a completeness check between source and generated object IDs.

### Phase 3: Change detection and integrations

- Add `celofast km pull --check` and object-level diffs.
- Accept generated attributes in the existing query API.
- Integrate generated objects with View inputs where identities match.
- Document application, CI, and code-review workflows.

### Follow-up opportunities

- Add specialized behavior for actions, anomalies, event logs, and custom
  objects already represented generically in the first release.
- Generate TypeScript from the same normalized schema.
- Build an IDE schema browser on top of the generated object metadata.
- Generate documentation sites or reference pages from the SDK.
- Compare draft and published KM SDKs before release.

## 24. Success measures

- Developers can discover a KM's usable objects without opening Studio.
- New applications use generated objects instead of duplicating KM IDs or PQL.
- CI catches breaking KM changes before deployment.
- One generated object is reusable across multiple Celofast capabilities.
- Pull succeeds consistently across the supported KM fixture set and lifecycle
  modes.
- Time required to integrate an existing KM into a Python application falls
  materially compared with manual metadata inspection.

## 25. Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| PyCelonis metadata differs between versions or modes | Generated SDKs are incomplete or inconsistent | Isolate adapters and test sanitized draft/published fixtures |
| PQL is altered during generation | Generated objects change business semantics | Preserve PQL verbatim and avoid parsing or optimization in the first release |
| Generated Python names collide | Object access becomes ambiguous | Use deterministic normalization and stable collision suffixes |
| Metadata does not provide a reliable type | Type hints become misleading | Generate `Any` and a warning rather than guessing |
| Users edit generated files | The next pull destroys application changes | Mark outputs clearly and keep application extensions outside the generated directory |
| Users expect local changes to update Celonis | Unsafe operational expectations | Use `pull`, provide no `sync` or `push`, and keep runtime objects immutable |
| Generated SDKs expose sensitive PQL | Business logic is committed too broadly | Document repository controls and never include credentials or data |
| Full KM generation creates a very large package | Slow generation and poor navigation | Partition deterministically by category and record, avoid eager runtime work, and benchmark large fixtures; completeness remains non-negotiable |
| KM item removal breaks application imports | Builds fail after regeneration | Treat this as intentional contract validation and provide clear object-level diffs |

## 26. Open questions

1. Should generated access paths use only Pythonic `snake_case`, or also expose
   exact-ID aliases such as `NumberNameConcat`?
2. Which metadata fields should be first-class properties versus preserved in
   an immutable `metadata` mapping?
3. Should internal notes be emitted into generated code or excluded by
   default?
4. Should documentation-only changes cause `pull --check` to fail?
5. Should PQL be stored in generated Python or in a sidecar manifest loaded by
   the generated objects?
6. What is the correct runtime representation for KPI and filter semantics:
   embedded definitions, symbolic references, or both?
7. Should the generated root expose only object instances or also export each
   generated record class for extension and testing?

## 27. Recommendation

Proceed with an end-to-end first release centered on the complete generated KM
object graph:

1. Pull one KM.
2. Generate every object in its effective content, using specialized types for
   the initial core categories and `GenericKnowledgeObject` for the rest.
3. Verify source-to-output completeness by ID and object count.
4. Preserve the complete metadata shown in the plant example.
5. Provide static `Attribute[T]` types and offline object discovery.
6. Allow a generated attribute to flow into the existing Celofast query
   execution path as proof that the object is functional.
7. Add deterministic re-pull and `--check` behavior.

This establishes a complete SDK foundation from the beginning. Later releases
expand category-specific behavior and consuming Celofast features without
changing the guarantee that the full KM is present.

[palantir-osdk]: https://www.palantir.com/docs/foundry/ontology-sdk/overview/
