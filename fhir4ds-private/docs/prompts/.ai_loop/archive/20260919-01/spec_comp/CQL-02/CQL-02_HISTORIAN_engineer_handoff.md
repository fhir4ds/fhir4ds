# Engineer Handoff — CQL-02 HISTORIAN, iteration 1 (2026-08-19)

## Fixed (all translator/UDF layer; no extension rebuild required)

### QA-001 (HIGH) — ValueSet/CodeSystem define-alias membership emitted invalid SQL
- Reproducer: `define VSDef: "Example VS"` / `define CSDef: LOINC`; `X in VSDef` /
  `"Systolic" in CSDef` emitted `... IN '{"id":...}'` → ParserException on BOTH backends.
- Root cause: `_translate_in_op` resolved only direct valueset identifiers
  (`_resolve_valueset_identifier`) and required `expr.right.name in codesystems`;
  define aliases fell through to generic SQL IN with the structured clinical JSON.
- Fix (`fhir4ds/cql/translator/expressions/_operators.py`): `_resolve_valueset_identifier`
  now follows Identifier/QualifiedIdentifier define-alias chains via
  `_definition_source_ast` (depth-capped 4); new `_resolve_codesystem_identifier`
  with the same discipline; the codesystem membership branch resolves aliases to
  the canonical URL. Only chains terminating at an actual valueset/codesystem
  declaration resolve — no silent fallback for non-terminology aliases.
- Note: `ExpandValueSet(VSDef)` was verified NOT affected (the SQL macro already
  unwraps `$.id` from structured JSON).

### QA-002 (HIGH) — `Concept { } in CS` emitted `json_object() IN '<CS JSON>'`
- Root cause: `_code_entries_from_ast` returned None for the empty Concept selector
  (no `codes` element), falling through to the generic membership path.
- Fix: `Concept { }` (no codes element) folds to an empty code-entry list → membership
  in CodeSystem/ValueSet folds to FALSE (`Concept { } in VS/CS` → FALSE). A
  present-but-unparsed `codes` element still returns None (runtime evaluation) so
  non-empty concepts are never silently emptied.

### QA-003 (MEDIUM) — Python fallback `in_valueset` raised instead of returning NULL
- Root cause: `fhir4ds/cql/duckdb/extension.py` registered a placeholder
  `in_valueset` that raised `duckdb.InvalidInputException` when no valueset data
  was loaded, while the native C++ path returns SQL NULL.
- Fix: placeholder returns SQL NULL with a warn-once log message preserving the
  register_valueset_udfs guidance; loaded-cache override behavior unchanged.

## Stale test expectations repaired (doctrine-aligned, pre-existing in campaign tree)
- `test_arithmetic_operator_parity.py::test_cql_arithmetic_expressions_parse_and_translate`:
  `DivideCheck` now expects `cqlDivide` (CQL-01 exact-division doctrine), not `NULLIF`.
- `test_arithmetic_part2_parity.py`: MaxInt/MinInt now expect
  `CAST(2147483647 AS INTEGER)` / `CAST(-2147483648 AS INTEGER)` (CQL-01 EXPLORER
  typed min/max lowering).
- `test_nullological_parity.py::QuantityValueRatio`: expects `Decimal('5.55555556')`
  (exact DECIMAL(38,8) cqlDivide) instead of DOUBLE `5.555555555555555`.

## Validation
- New dual-backend regression tests: 4 `test_cql02_historian_*` tests in
  `fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py` (alias VS
  membership SQL-shape + execution, alias CS membership, empty-Concept fold,
  fallback NULL parity).
- `fhir4ds/cql/duckdb/tests/integration`: 296 passed, 1 skipped.
- `fhir4ds/cql/tests/unit`: 1612 passed.
- Full conformance: **2832/2832** (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47) — baseline held.

## Files changed
- fhir4ds/cql/translator/expressions/_operators.py (QA-001, QA-002)
- fhir4ds/cql/duckdb/extension.py (QA-003)
- fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py (new tests)
- fhir4ds/cql/duckdb/tests/integration/{test_arithmetic_operator_parity,test_arithmetic_part2_parity,test_nullological_parity}.py (stale expectations)
