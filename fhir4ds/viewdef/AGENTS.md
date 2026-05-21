# ViewDefinition Agent Notes

## Known Fragile Areas
- SOF-VD-12 EXPLORER verified clean (2026-05-20): Boundary probes for
  combined Shareable+Tabular `meta.profile` declarations with version suffixes,
  unsupported profile URL aliases, top-level unsupported `mapping` input,
  official JSON field-name round trips, explicit XML-unsupported behavior, and
  metadata-heavy DuckDB execution all passed against current source. Unsupported
  `mapping` is ignored and omitted from `to_dict()`; keep this documented
  behavior consistent unless the logical model adds a supported mapping field.
- SOF-VD-12 HISTORIAN verified clean (2026-05-20): Fresh parser,
  serializer, SQL generation, and DuckDB execution probes confirmed
  Shareable/Tabular `meta.profile` constraints, CanonicalResource metadata
  retention, official JSON field-name round trips, explicit XML-unsupported
  behavior, and ignored unsupported top-level `mapping` input. Keep official
  example execution paired across native C++ FHIRPath registration and forced
  Python fallback when revisiting profile/metadata behavior.
- SOF-VD-12 SKEPTIC fixed (2026-05-20): ViewDefinition
  `meta.profile` must activate supported logical-model profile constraints.
  ShareableViewDefinition requires root `url`, `name`, `fhirVersion`, and
  every `select.column.type`; TabularViewDefinition forbids collection columns
  and non-primitive column types. Root CanonicalResource metadata such as
  `url`, `version`, and `status` is retained by the parser/serializer without
  changing generated SQL execution. XML parsing is intentionally
  unsupported unless a dedicated XML parser is added; document that boundary
  explicitly instead of surfacing only a generic invalid-JSON parse error.
- SOF-VD-11 EXPLORER verified (2026-05-20): ViewDefinition runner probes for
  Patient key projection, Observation filtering, Patient.address `forEach`,
  `forEachOrNull`, `%rowIndex` filters, collection typed output, and parser
  rejection paths pass against the current source tree under both native C++
  DuckDB registration and forced Python fallback. Scratch scripts under
  `.ai_loop/.temp` must prepend the repo root to `sys.path`; otherwise they can
  accidentally import an installed package and report stale ViewDefinition
  behavior.
- SOF-VD-11 HISTORIAN fixed (2026-05-20): SQL-on-FHIR View Runner helper
  functions `getResourceKey()` and `getReferenceKey()` must work under both
  native C++ DuckDB registration and forced Python fallback. The Python
  fallback already returned canonical `ResourceType/id` keys, but native C++
  treated these functions as unknown and generated NULL rows in official
  PatientDemographics/PatientAddresses/UsCoreBloodPressures-style
  ViewDefinitions. Keep runner example tests paired across native/fallback and
  rebuild/copy `fhirpath.duckdb_extension` after touching native FHIRPath.
- SOF-VD-11 SKEPTIC fixed (2026-05-20): Observation ViewDefinition
  execution with a decimal `valueQuantity.value` column must work on both
  native C++ registration and forced Python fallback. The generator's runtime
  type guard asks FHIRPath for `(valueQuantity.value).type().name`; fallback
  FHIRPath must report numeric Quantity values as `decimal`, not the broad
  `.value` suffix fallback `string`, or valid filtered Observation views raise
  a collection/type guard error only on fallback.
- SOF-VD-10 EXPLORER fixed (2026-05-20): strict
  `parse_view_definition()` must reject present JSON null for repeating
  logical-model fields such as `constant`, `profile`, and `fhirVersion`.
  Absence remains valid for optional fields, but a present field must preserve
  FHIR JSON shape rules: repeating elements are arrays and properties are not
  null. Keep `ViewDefinition.from_dict()` aligned through its parser
  delegation, and keep permissive `validate_view_definition()` limited to
  direct dataclass warning inspection.
- SOF-VD-10 HISTORIAN fixed (2026-05-20): keep parser and generator strict for
  SQL-on-FHIR `sql-expressions`, but keep
  `parser.validate_view_definition()` permissive. It should collect warnings
  for direct-dataclass issues such as combined `forEach`/`forEachOrNull`/
  `repeat`, missing `column.path`, and missing `column.name`; it must not raise
  before returning its warning list. Strict parse and SQL generation paths have
  separate guards for the same error constraints.
- SOF-VD-10 SKEPTIC fixed (2026-05-20): parser/public
  `ViewDefinition.from_dict()` enforce the SQL-on-FHIR `sql-name` invariant on
  optional `ViewDefinition.name`, and strict SQL generation validates direct
  dataclass root `name`, `fhirVersion`, and `Constant.name`/`value[x]`
  bypasses before SQL generation. Keep parser coverage for required
  `resource`, `select`, `column.path`, `column.name`, `constant.name`,
  `constant.value[x]`, `where.path`, ResourceType binding, FHIRVersion binding,
  and forEach/forEachOrNull/repeat mutual exclusion aligned with direct
  generator guard paths while preserving `validate_view_definition()` as a
  permissive warning API.
- SOF-VD-09 SKEPTIC fixed (2026-05-20): root/select
  `where` predicates must not coerce non-Boolean FHIRPath results into
  inclusion. ViewDefinition SQL uses exact `fhirpath_json(...) = '[true]'`
  predicates instead of the permissive public `fhirpath_bool` convenience UDF,
  so numeric/string results such as `valueInteger`, `1`, or `"true"` do not
  satisfy root/select where constraints. Keep native C++ and forced Python
  fallback parity for this generated SQL boundary.
- SOF-VD-09 SKEPTIC fixed (2026-05-20): `where.description` is optional
  string/markdown metadata and should be validated at parser,
  `ViewDefinition.from_dict()`, and generator direct-dataclass boundaries while
  preserving valid strings. Do not preserve present numeric/null description
  values as opaque dict extras.
- SOF-VD-08 EXPLORER fixed (2026-05-20): the deprecated/importable
  `UnionGenerator.validate_union_columns()` helper is still a public
  compatibility surface and must validate the same effective union branch
  schema as `generate_union_all()` and `SQLGenerator`: column name, order,
  declared FHIR type, and `collection` cardinality. Name-only warnings can
  falsely bless spec-invalid `unionAll` branches even though execution rejects
  them later; the helper now compares effective schema triples.
- SOF-VD-08 HISTORIAN fixed (2026-05-20): the legacy/importable
  `fhir4ds.viewdef.union.generate_union_all()` helper must preserve the same
  rowset semantics as main `SQLGenerator` for branch `forEach`,
  `forEachOrNull`, `repeat`, nested `select`, branch `where`, and nested
  `unionAll`. Do not implement direct union helpers by only rendering branch
  columns against the root resource; that silently drops iterator rows and
  nested branch columns even though the main ViewDefinition generator is
  correct.
- SOF-VD-08 SKEPTIC fixed (2026-05-20): `select.unionAll` rowsets compose
  like ordinary `select` rowsets. Multiple sibling unionAll groups, and nested
  unionAll groups under a parent select, must be expanded into branch
  combinations and cross-joined with sibling selects rather than concatenated
  as independent SQL UNION groups. Effective output-schema validation must also
  include each unionAll rowset's first-branch schema so sibling union groups
  cannot silently project the same column name.
- SOF-VD-08 SKEPTIC fixed (2026-05-20): A unionAll branch may contain direct
  columns plus nested select/unionAll columns. Branch schema collection and SQL
  generation must preserve both the branch-local columns and nested union
  columns in column order; treating a branch's direct columns as a reason to
  ignore nested unionAll output silently drops data.
- SOF-VD-07 EXPLORER fixed (2026-05-20): `select.repeat` over raw deeply
  nested JSON must preserve native C++ and forced Python fallback parity beyond
  Python/orjson recursion limits. The fallback `fhirpath_repeat` path now
  parses with a depth-derived recursion budget under the repeat fallback
  recursion-limit lock, traverses iteratively, and uses iterative JSON
  serialization for repeated child nodes. Keep raw JSON ViewDefinition coverage
  for nested `QuestionnaireResponse.item` depth above the default Python
  recursion ceiling; dict fixtures serialized with `json.dumps` can hide this
  class of bug before DuckDB is reached.
- SOF-VD-07 HISTORIAN fixed (2026-05-20): ViewDefinition
  `select.repeat` columns and repeat entries may explicitly use `$this` as the
  current repeated-node focus. Keep forced Python fallback and native C++
  parity for `$this.linkId`, `$this.text.exists()`, and repeat expressions
  such as `$this.item`; otherwise columns can silently return NULL only on the
  fallback path even though ordinary relative paths like `linkId` work.
- SOF-VD-07 SKEPTIC fixed (2026-05-20): `select.repeat` entries are
  FHIRPath expressions, not only dotted JSON keys. ViewDefinition SQL routes
  repeat traversal through `fhirpath_repeat`, so the Python fallback and native
  C++ UDF must both evaluate each repeat expression at the current repeated
  node, recursively visit object results to any parsed depth, union duplicate
  node hits across paths, and preserve column evaluation against each repeated
  node. Keep parser/generator validation rejecting scalar JSON `repeat:
  "path"`; present `repeat` is a 0..* array field.
- SOF-VD-06 EXPLORER fixed (2026-05-20): `%rowIndex` is a
  ViewDefinition/FHIRPath environment variable, not only a standalone pseudo
  column. Columns and select `where` predicates inside `forEach`/
  `forEachOrNull` must support `%rowIndex` embedded in larger FHIRPath
  expressions such as `iif(%rowIndex = 0, ...)` or `%rowIndex = 1`; otherwise
  the DuckDB FHIRPath UDF sees an undefined variable and silently returns
  NULL/empty rows. The generator now substitutes the active row-index SQL
  value into the FHIRPath expression argument before calling DuckDB UDFs.
- SOF-VD-06 EXPLORER fixed (2026-05-20): Embedded `%resource` and
  `%rootResource` references inside iterator expressions must still target the
  root resource, not the unnested item. Root-only embedded expressions route to
  the root input; expressions that mix root variables with current-focus paths
  or `%context` fail fast because the public DuckDB FHIRPath UDF accepts one
  JSON context input.
- SOF-VD-06 HISTORIAN fixed (2026-05-20): The SQL-on-FHIR
  `sql-expressions` constraint applies to all three iterator fields. Parser,
  `ViewDefinition.from_dict()`, direct dataclass validation, and generator
  guard paths must reject any `select` that combines `forEach`,
  `forEachOrNull`, and/or `repeat`; do not defer this to SQL generation only.
- SOF-VD-06 HISTORIAN fixed (2026-05-20): Leading `%context.`,
  `%resource.`, and `%rootResource.` expressions may include ordinary FHIRPath
  functions or predicates, not only dot navigation. Route the whole tail to the
  correct current/root JSON input in ViewDefinition SQL generation. If an
  iterated expression mixes root and current built-ins in one FHIRPath string,
  fail fast rather than evaluating it against the iterator alias and returning
  plausible but wrong rows.
- SOF-VD-06 SKEPTIC fixed (2026-05-20): ViewDefinition iterators change the
  current column evaluation context to the unnested element, but FHIRPath
  `%resource` and `%rootResource` must still resolve to the containing/root
  resource for that element. Do not blindly pass `%resource.*` or
  `%rootResource.*` paths to `fhirpath_*` with the iterator alias as the input;
  generator routing preserves root-resource context while keeping `%context`
  relative to the iterated element and `%rowIndex` relative to the iterator.
- SOF-VD-05 EXPLORER fixed (2026-05-20): `unionAll` branch schema
  validation must compare effective column name, order, declared FHIR type, and
  `collection` cardinality. Matching names alone are insufficient; otherwise a
  spec-invalid union can be accepted and coerced only by the physical SQL
  backend. Direct generator guard paths must also validate recursive
  `select`/`unionAll`/`column` containers as arrays of dataclass objects so
  public dataclass construction cannot bypass parser shape checks or fail with
  raw `TypeError`/`AttributeError`.
- SOF-VD-05 HISTORIAN fixed (2026-05-20): nested `select` is a full
  recursive `contentReference` to `ViewDefinition.select`, so a child
  `select` containing `unionAll` must be processed at any depth even when no
  parent `forEach`/`forEachOrNull`/`repeat` context exists. Do not limit nested
  union hoisting to iterator parents; default `$this` wrapper selects must
  still emit the union branch rows and combine parent columns with branch
  columns.
- SOF-VD-04 EXPLORER fixed (2026-05-20): `collection=true` primitive
  typed columns must preserve the declared primitive element type in generated
  DuckDB output. `fhirpath()` returns `VARCHAR[]`, so generator collection
  expressions explicitly cast integer/boolean/numeric primitive declarations
  with DuckDB `list_transform` while preserving string/date/time and complex
  JSON representations.
- SOF-VD-04 HISTORIAN fixed (2026-05-20): `column.type` element ID
  notation such as `Observation.referenceRange` must not be fed directly into
  simple `type().name` equality guards. FHIRPath engines may report a
  datatype-like runtime name such as `Range`/`range` for that backbone element;
  SQL generation should preserve element-ID declarations while still enforcing
  cardinality.
- SOF-VD-04 HISTORIAN fixed (2026-05-20): `$this` column expressions bypass
  the normal simple-path runtime type guard path. Keep explicit SQL JSON-shape
  safeguards for non-primitive `$this` values when `column.type` is unset or
  primitive, especially inside `forEach` contexts where `$this` can be a
  complex element.
- SOF-VD-04 SKEPTIC fixed (2026-05-20): `column.collection` defaults to
  false, and public SQL generation/execution must report an error when a
  non-collection column produces multiple values. Do not rely on permissive
  `fhirpath_text()` first-value behavior for scalar ViewDefinition columns.
- SOF-VD-04 SKEPTIC fixed (2026-05-20): `column.type` is a FHIR
  StructureDefinition URI field, not only the local enum spelling. Preserve
  relative/full FHIR URIs, require explicit type for non-primitive outputs, and
  report primitive/non-primitive mismatches instead of silently returning text
  or NULL.
- SOF-VD-04 SKEPTIC fixed (2026-05-20): `column.tag` is a 0..* backbone
  element with required string `name` and `value`. Parser, public
  `ViewDefinition.from_dict()`, and direct dataclass/generator guard paths must
  validate and preserve tags; database/type-hint tags are metadata unless an
  implementation explicitly handles them.
- Milestone code review finding (2026-05-20, OPEN): Public
  `ViewDefinition.from_dict()` must stay in lockstep with
  `parse_view_definition()` for root metadata and `where` parsing. It currently
  accepts invalid `resource`/`profile`/`fhirVersion` shapes and can silently
  drop parser-supported root `where` dict/string filters during SQL generation.
  Remediation should reuse shared parser/type helpers or delegate dict
  construction through the parser, with regression tests at both boundaries.
- Milestone code review finding (2026-05-20, OPEN): Legacy public join helpers
  in `join.py` interpolate join aliases/resources into generated SQL. Validate
  `join.name` as SQL-on-FHIR `sql-name`, validate `join.resource` against
  ResourceType metadata, and quote aliases/table references before treating
  joins as executable SQL generation surface.
- SOF-VD-03 EXPLORER fixed (2026-05-20): Select iteration fields need
  logical-model shape validation before SQL generation. `forEach` and
  `forEachOrNull` are optional string FHIRPath expressions, while `repeat` is a
  repeating string field; do not coerce arbitrary iterables such as dicts into
  repeat path lists.
- SOF-VD-03 EXPLORER fixed (2026-05-20): `column.collection` is a boolean
  logical-model field. String values such as `"false"` must not be accepted or
  interpreted through Python truthiness, because that changes scalar columns
  into collection-valued SQL output.
- SOF-VD-03 HISTORIAN fixed (2026-05-20): Treat present `null` values for
  repeating select containers (`column`, nested `select`, `unionAll`) as invalid
  parser/public-constructor input, not as absent arrays. SQL-on-FHIR inherits
  FHIR JSON repeating-element shape: present repeating elements are arrays.
- SOF-VD-03 HISTORIAN fixed (2026-05-20): Duplicate output column-name checks
  must include the effective schema produced by `unionAll` plus sibling/parent
  columns. Matching names across branches are required, but a branch column must
  not collide with sibling columns projected into the same output row.
- SOF-VD-03 SKEPTIC fixed (2026-05-20): Select/column parser validation
  must enforce logical-model container and primitive shapes at the parser and
  public `ViewDefinition.from_dict()` boundaries. `ViewDefinition.select` is a
  non-empty array, `select.column`/nested `select`/`unionAll` are arrays of
  objects, `column.path` and `column.name` are non-empty strings, `column.name`
  must satisfy SQL-on-FHIR `sql-name` without a leading underscore, and
  `column.description` must be markdown/string metadata when present. Generic
  SQL table identifier quoting remains separate from ViewDefinition output
  column sql-name validation.
- SOF-VD-02 EXPLORER fixed (2026-05-20): Constant substitution must be
  FHIRPath-lexical, not regex-only. `%name` inside FHIRPath string literals is
  literal text, while `%name` outside literals is an external constant; string
  constant values must be escaped as FHIRPath string literals before the
  generated FHIRPath expression is SQL-escaped.
- SOF-VD-02 EXPLORER fixed (2026-05-20): `valueInteger64` is a FHIR primitive
  represented as a JSON string in FHIR JSON. ViewDefinition parsing must reject
  JSON-number `valueInteger64` even if the numeric range is otherwise valid.
- SOF-VD-02 HISTORIAN fixed (2026-05-20): Constant validation must stay
  primitive-only for `ViewDefinition.constant.value[x]`. The current SQL-on-FHIR
  choice list does not include historical complex `valueCoding` or
  `valueCodeableConcept`, and FHIR primitive values need type/range/lexical
  validation before parser or public constructor acceptance.
- SOF-VD-02 HISTORIAN fixed (2026-05-20): Public convenience constructors must
  parse the spec singular `constant` field consistently with
  `parse_view_definition`; otherwise constants disappear before `%name`
  validation/substitution reaches SQL generation.
- SOF-VD-02 SKEPTIC fixed (2026-05-20): `ViewDefinition.constant.name`
  must enforce the SQL-on-FHIR `sql-name` invariant
  `^[A-Za-z][A-Za-z0-9_]*$`; accepting names such as `_bad`, `bad-name`, or
  `bad.name` lets parser state and FHIRPath `%name` reference extraction drift.
- SOF-VD-02 SKEPTIC fixed (2026-05-20): `ViewDefinition.constant.value[x]`
  must be exactly one supported primitive choice. Do not silently choose the
  first of multiple `value*` fields, accept unknown `valueFoo`, or rely on
  fallback casing for supported choices such as canonical and integer64.
- SOF-VD-01 SKEPTIC fixed (2026-05-20): `ViewDefinition.resource` must remain a single required FHIR `ResourceType` code. Parser and generator now reject arrays and unknown resource codes; do not reintroduce array/multi-resource root support unless the SQL-on-FHIR logical model changes.
- SOF-VD-01 SKEPTIC fixed (2026-05-20): `ViewDefinition.profile` and `ViewDefinition.fhirVersion` are logical-model declarations and must be parsed/preserved with validation even though they do not currently alter generated SQL.

## NOT A BUG Registry

- SOF-VD-09 EXPLORER verified clean (2026-05-20): Root `where`
  predicates that produce empty/null, non-Boolean strings such as `"true"`,
  or multi-item Boolean collections such as `true | false` are not inclusion
  signals. Generated SQL requires exact singleton Boolean true and preserves
  root-resource scope for `$this`, leading `%resource`, and embedded
  `%resource`/`%rootResource` expressions in both native C++ and forced Python
  fallback execution.
- SOF-VD-09 HISTORIAN verified clean (2026-05-20): A valid FHIRPath
  expression used as root `where` that returns a non-Boolean scalar, such as
  `id`, `'true'`, or `1`, is not a row-inclusion signal. Generated
  ViewDefinition SQL requires exact singleton Boolean true
  (`fhirpath_json(...) = '[true]'`), so these cases are excluded
  row-resiliently in both native C++ and forced Python fallback execution.
- SOF-VD-05 SKEPTIC (2026-05-20): A nested child `forEach` under an
  enclosing `forEachOrNull` keeps its own inner-flattening semantics. If the
  outer `forEachOrNull` creates a NULL row and the child `forEach` has no
  collection to iterate, that child branch may produce no row. This matches the
  SQL-on-FHIR functional model precedence (`forEachOrNull` then `select`) and
  the official `foreach.json` unionAll cases, where null-preserved rows are not
  duplicated by child `forEach` branches.
- SOF-VD-01 SKEPTIC (2026-05-20): With `SQLGenerator(source_table="resources")`, generated SQL must add a `json_extract_string(t.resource, '$.resourceType') = '<resource>'` filter. This preserves one ViewDefinition's single root resource type when several resource types share one physical table.
- SOF-VD-01 HISTORIAN verified clean (2026-05-20): `profile` and `fhirVersion` are logical-model declarations parsed and preserved on `ViewDefinition`; they do not currently change generated SQL. Root resource execution still comes from `resource` plus the physical table/resourceType filter contract.
- SOF-VD-01 EXPLORER verified clean (2026-05-20): A root `Patient` ViewDefinition over a shared mixed-resource table should filter out non-Patient rows while still allowing zero-or-more output rows per Patient. `forEachOrNull` preserving a Patient row with null nested columns is required behavior, not a leak from the resourceType filter.

## Architecture

- SOF-VD-09 SKEPTIC (2026-05-20): Treat `where` as a
  ViewDefinition-specific exact-Boolean SQL boundary. Public convenience UDFs
  such as `fhirpath_bool` may remain permissive for broader SQL callers, but
  generated SQL-on-FHIR filters must require the FHIRPath result to serialize
  as singleton Boolean true and must preserve root/current context routing.
  Keep `where` metadata validation centralized in `types.py` and reused by
  parser, public constructor, and generator guard paths.
- SOF-VD-08 EXPLORER (2026-05-20): Keep `unionAll` effective schema
  extraction centralized. Deprecated/importable helpers such as
  `UnionGenerator.validate_union_columns()` may be legacy, but while public
  they must delegate to the same `(name, type, collection)` schema boundary as
  `generate_union_all()` and main `SQLGenerator`.
- SOF-VD-08 SKEPTIC (2026-05-20): Treat `unionAll` as a rowset-producing
  select expression, not as a top-level SQL string mode. SQL generation expands
  union branches into alternatives, then composes those alternatives with
  sibling selects via the same rowset cross-join semantics as ordinary nested
  selects. Effective schema collection is the shared source for duplicate
  output-name validation and branch compatibility.
- SOF-VD-05 EXPLORER (2026-05-20): Treat `unionAll` output schema as
  name/order/FHIR-type/collection-cardinality, not just a sequence of SQL
  aliases. Parser validation and direct generator dataclass guardrails must
  enforce the same recursive container boundaries for `column`, `select`, and
  `unionAll` before SQL generation starts.
- SOF-VD-05 HISTORIAN (2026-05-20): Treat nested `select` and `unionAll`
  as the same recursive `ViewDefinition.select` grammar at every depth.
  Parent context inheritance includes explicit iterators and the implicit
  default `$this` context; hoisting/generation logic must not special-case
  only iterator parents.
- SOF-VD-05 SKEPTIC (2026-05-20): Preserve the official row-composition
  layering for nested selects. `forEachOrNull` is a row-preserving iterator for
  its own expression, while descendant `select`, child `forEach`, and
  `unionAll` composition still follow their normal row-set semantics; do not
  broaden child iteration behavior based only on an enclosing null-preserved
  context.
- SOF-VD-03 EXPLORER (2026-05-20): Keep select iteration field and
  `column.collection` validation centralized in `types.py` helpers and reused
  by parser, public `ViewDefinition.from_dict()`, and generator direct-input
  guard paths. Parser/public constructors should fail typed logical-model shape
  errors before SQL generation; generator guards are the final safety net for
  manually constructed dataclasses.
- SOF-VD-03 HISTORIAN (2026-05-20): Keep `unionAll` validation split into two
  concerns: branch alternatives must match each other by column name/order, and
  each effective branch schema must remain duplicate-free against sibling and
  parent projected columns. Do not collapse those rules into a global duplicate
  check that rejects legitimate matching branch schemas.
- SOF-VD-03 SKEPTIC (2026-05-20): Keep ViewDefinition output column
  validation centralized through shared type helpers and reused by parser and
  public `ViewDefinition.from_dict()`. Keep generator-side column-name
  validation as the final guard for direct dataclass construction, but do not
  reuse the stricter SQL-on-FHIR `sql-name` rule for implementation-controlled
  table references.
- SOF-VD-04 SKEPTIC (2026-05-20): Keep `collection`, `type`, and `tag`
  validation split by responsibility: parser/types enforce logical-model JSON
  shape and URI/tag metadata, while generator execution guards enforce
  result-cardinality and only safe runtime type checks. Broad `type().name`
  wrapping over all FHIRPath expressions regresses valid literals, functions,
  and nested unrolled element contexts.
- SOF-VD-04 HISTORIAN (2026-05-20): Element-ID `column.type` declarations are
  FHIR element-shape metadata, not runtime `type().name` strings. `$this`
  paths need their own JSON-shape guard because they intentionally bypass
  normal path navigation and may point at a complex current focus.
- SOF-VD-01 EXPLORER (2026-05-20): Keep root metadata validation centralized in `metadata.py`; parser and generator should consume shared ResourceType/FHIRVersion constants instead of drifting into separate allowlists.
- SOF-VD-02 SKEPTIC (2026-05-20): Keep constant `name` and `value[x]` validation metadata centralized in `types.py` so parser and public convenience constructors enforce the same supported field set and exactly-one behavior.
- SOF-VD-02 HISTORIAN (2026-05-20): Keep FHIR primitive constant value
  validation centralized before substitution. SQL generation should only consume
  parsed `Constant` objects through `ConstantResolver`; it must not rediscover
  `value[x]` fields or rely on DuckDB/FHIRPath coercion to reject invalid
  primitive constants later.
- SOF-VD-02 EXPLORER (2026-05-20): Keep FHIRPath lexical scanning for
  constants centralized in `constants.py`; generator validation and substitution
  must share the same scanner so `%name` handling cannot drift between
  preflight and execution.
