# QA Handoff - SOF-VD-07 HISTORIAN

Scope: SQL-on-FHIR ViewDefinition `select.repeat` compliance. Personality:
HISTORIAN.

Spec anchors checked:
- SQL-on-FHIR latest ViewDefinition logical model defines `select.repeat` as
  `0..* string` FHIRPath expressions and includes it in the mutual-exclusion
  invariant with `forEach` and `forEachOrNull`.
- SQL-on-FHIR repeat semantics start at the current context node, evaluate each
  repeat path, recursively apply the same path set to each result, and union
  results from all levels and paths.
- `%rowIndex` is defined in `forEach`, `forEachOrNull`, and `repeat` contexts.

Fresh probe: `.temp/qa/sof_vd07_historian_probe.py`

Coverage:
- Official QuestionnaireResponse-style recursive flattening with
  `repeat: ["item", "answer.item"]`.
- Multiple repeat paths, duplicate-path union behavior, and deterministic
  repeated-node `%rowIndex` values.
- Column evaluation against repeated-node context for `linkId`,
  `$this.linkId`, and `$this.text.exists()`.
- Explicit `$this` repeat path as a cycle/visited-set guard.
- Deep nested traversal on forced Python fallback and native-loaded DuckDB
  where available.
- Parser, `ViewDefinition.from_dict()`, `Select.to_dict()`, and
  `SQLGenerator.generate()` rejection for malformed repeat values and iterator
  mutual exclusion.

Findings: no product defects found. The current SKEPTIC empty-repeat fix held
across all checked boundaries.

Validation:
- Fresh HISTORIAN probe: PASS.
- Focused repeat/parser/generator pytest: 20 passed.
- Full ViewDefinition pytest: 952 passed.
- ViewDefinition conformance: 134/134.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.
