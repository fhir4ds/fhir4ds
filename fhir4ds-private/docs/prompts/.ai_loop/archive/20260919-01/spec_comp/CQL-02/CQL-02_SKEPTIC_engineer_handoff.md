# Engineer Handoff — CQL-02 (Clinical Types), iteration 1 (2026-08-19)

## Fixed (all RESOLVED, both Python fallback and native C++ verified, conformance 2832/2832)

- QA-001 (HIGH): Code/Concept `~` now applies CQL string equivalence
  (casefold + whitespace normalization) to code and system elements.
  `fhir4ds/cql/translator/expressions/_operators.py` `_translate_equivalence_op`
  (`_cql_string_equivalence_key` feeding `_code_key`); also fixes the
  closure-aware literal-match arm (keys derive from `_code_key`).
- QA-002 (HIGH): `Concept { codes: { "NamedCode", ... } }` now folds to
  structured Concept JSON via `_fold_static_concept_instance` in
  `fhir4ds/cql/translator/expressions/_lists.py` (named-code members no
  longer double-serialize as strings; falls back to the generic runtime
  path only for dynamic members).
- QA-003 (HIGH): `.codes` member access on static clinical values folds to a
  `SQLArray` of Code JSON values (List<Code>) so `Count(concept.codes)`,
  membership, and distinct see a real list; `.code/.system/.version/.display`
  fold to literals. `_static_clinical_value_object` also now folds
  `ToConcept(Code)` / `ToConcept(List<Code>)`.
  Files: `_operators.py`, `_property.py` (`_fold_static_clinical_property`).
- QA-004 (HIGH): statically-known clinical literal definitions (Code
  selector, Concept instance, ValueSet/CodeSystem refs, incl. chains of such
  defines) inline at reference sites from the top of `_translate_identifier`
  (`_core.py`, helper `_is_static_clinical_definition` in `_query.py`),
  replacing dangling patient-correlated CTE lookups that Binder-errored
  end-to-end. Generic String/Integer literal-define aliases share the shape
  mismatch — pre-existing, OUT OF CHUNK SCOPE, flagged for a CQL primitives
  followup (documented in AGENTS.md).
- QA-005 (LOW): INTENDED — static Code-in-CodeSystem membership is
  structural without terminology data. Documented in AGENTS.md.
- QA-006 (MEDIUM): stale pre-existing test expectations contradicting the
  CQL-01 doctrine (Avg=cqlDivide, DECIMAL(38,8) aggregate rounding,
  ToDecimal rounds beyond-scale strings). Updated
  `test_aggregate_parity.py` (avg-substring + 1e-7 tolerance) and
  `test_primitive_parity.py` (ToDecimal('1.123456789') → 1.12345679).

## Regression coverage added
`fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py`: 4 new
dual-backend tests (`test_cql02_skeptic_*`) including full-pipeline
(`translate_library_to_sql`) execution for define aliases. File now 18/18.

## Validation
- Clinical type parity 18/18; clinical operator + conversion function parity
  33/33; aggregate 9/9; primitive 14/14; CQL unit tests + key parity files
  4992 passed (after QA-006 staleness fixes; the two failing assertions were
  pre-existing doctrine drift, verified unrelated to this chunk's edits).
- Full conformance: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47 — OVERALL 2832/2832 (baseline holds).

## Notes for Architect
- All fixes are translator-layer (Python); no C++ rebuild required (verified
  native parity through the already-deployed extension).
- Followup candidate: generic scalar literal define aliases
  (`define S: 'hello'; define T: S` → Binder error) share QA-004's root cause
  but are primitive-scope (CQL-01 territory); recommend a dedicated chunk.
