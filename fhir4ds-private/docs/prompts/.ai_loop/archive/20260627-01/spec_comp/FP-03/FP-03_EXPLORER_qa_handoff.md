# QA Handoff - SPEC FP-03 EXPLORER

## Scope

- Chunk: SPEC COMPLIANCE FP-03, FHIRPath §5.1 Existence.
- Personality: EXPLORER.
- Spec source checked: HL7 FHIRPath continuous build, `input/pages/index.md`, §5.1 Existence and scoped-function rules.
- Required functions probed: `empty()`, `exists([criteria])`, `all(criteria)`, `allTrue()`, `anyTrue()`, `allFalse()`, `anyFalse()`, `subsetOf(other)`, `supersetOf(other)`, `count()`, `distinct()`, and `isDistinct()`.

## Hypotheses

1. Nested `exists(criteria)` / `all(criteria)` might return before validating every item with a non-Boolean criteria result.
2. Boolean aggregates might short-circuit on the first decisive Boolean and fail to reject a later non-Boolean item.
3. `subsetOf()` / `supersetOf()` arguments inside scoped expressions might regress to root-context evaluation.
4. `distinct()` / `isDistinct()` might use string identity instead of FHIRPath equality for structures, numerics, or compatible Quantities.
5. Native C++ and forced Python fallback public DuckDB wrappers might disagree on invalid arity row resilience or `fhirpath_is_valid()`.

## Fresh Probe

- Added `.temp/qa/fp03_explorer_fresh_probe.py`.
- The probe creates one native DuckDB connection and one forced Python fallback connection, compares `fhirpath`, `fhirpath_json`, `fhirpath_bool`, and `fhirpath_is_valid`, and asserts expected §5.1 results.
- Coverage: 32 composed/pathological expressions over empty inputs, nested criteria, Boolean aggregate type validation, scoped set comparisons, structural JSON equality, compatible Quantity equality, numeric/string de-duplication, and invalid helper arities.

## Results

- `python3 .temp/qa/fp03_explorer_fresh_probe.py` passed after correcting probe expectations for integer `count()` values and equality-set duplicate semantics.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py -q` passed, 13/13.
- No new product issues were opened.

## Issue Summary

- Opened: 0
- Resolved: 0
- Open remaining: 0
