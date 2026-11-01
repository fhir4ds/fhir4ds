# QA Handoff - FP-04 EXPLORER

Spec focus: FHIRPath Normative Release Section 5.2 Filtering and Projection:
`where(criteria)`, `select(projection)`, `repeat(projection)`, and
`ofType(type)`.

Personality: EXPLORER.

Spec grounding:
- `where(criteria)` returns only items whose criteria evaluates to singleton
  Boolean true; false or empty are excluded, and non-singleton/non-Boolean
  criteria is an evaluation error.
- `select(projection)` evaluates one projection expression for each input item
  and flattens projection collections into the result.
- `repeat(projection)` repeats one projection expression until no equality-new
  items are produced.
- `ofType(type)` keeps items of the requested model type or subclass; `type` is
  a model type specifier, not a runtime string expression.

Probe:
- Created `.temp/qa/fp04_explorer_probe.py`.
- Ran native C++ DuckDB registration and forced Python fallback registration in
  the same probe.
- Covered 5 EXPLORER passes: nested `where`, nested/flattening `select`,
  recursive `repeat`, type filtering/chained choice `ofType`, and malformed
  arity/type-specifier calls.

Findings:
- `QA-001` MEDIUM: native C++ accepts malformed Section 5.2 invocations and can
  return data instead of invalid/empty. Cases include `Patient.where()`,
  `item.where()`, `item.where(true, false).linkId`, `item.select()`,
  `item.select(linkId, item).count()`, `item.repeat()`, and
  `Patient.ofType('Patient').id`.
- `QA-002` HIGH: forced Python fallback drops nested choice values after a
  filtered resource projection. `entry.resource.ofType(Observation).value.ofType(Integer)`
  returns `7` in native C++ but empty/NULL in forced fallback.

Validation evidence:
- Probe summary: `mismatch_count=9`, `expectation_failure_count=8`.
- Full log: `.temp/qa/fp04_explorer_probe.log`.

Next phase:
- Fix native arity/type-specifier validation in the C++ parser/evaluator path.
- Fix fallback choice-type `ofType` resolution for nested resource paths such as
  `entry.resource.ofType(Observation).value.ofType(Integer)`.
- Add focused native/fallback parity tests for both issues.
