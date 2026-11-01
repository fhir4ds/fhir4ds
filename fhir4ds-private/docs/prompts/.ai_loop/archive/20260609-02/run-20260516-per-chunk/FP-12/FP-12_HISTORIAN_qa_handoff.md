# QA Handoff - FP-12 HISTORIAN

## Scope
- Chunk: FP-12
- Spec: FHIRPath Normative Release N1 sections 5.8 and 5.9
- Functions audited: `children()`, `descendants()`, `trace(name, [projection])`, `now()`, `timeOfDay()`, `today()`
- Personality: HISTORIAN

## Spec Grounding
- `children()` returns all immediate child nodes; ordering is undefined.
- `descendants()` returns all descendant nodes and excludes the input nodes; it is shorthand for `repeat(children())`.
- `trace(name, projection)` returns the original input unchanged and logs either the input or the projection result.
- `now()`, `timeOfDay()`, and `today()` return current DateTime, Time, and Date respectively; each must be deterministic within one expression. Timestamp source is implementation policy.

Source verified: https://hl7.org/fhirpath/N1/ lines 1544-1575.

## Hypotheses Tested
- Tree navigation might drop JSON null-valued children on one DuckDB backend.
- `descendants()` might include the input node or diverge from repeated child traversal.
- `trace(name, projection)` might return the projection instead of the original input.
- Current date/time functions might be missing or nondeterministic in native DuckDB.
- Native and forced Python fallback DuckDB surfaces might diverge for public `fhirpath`, `fhirpath_text`, and `fhirpath_json` outputs.

## Results
- No CRITICAL/HIGH/MEDIUM issues found.
- Native/C++ DuckDB extension loaded successfully and matched forced Python fallback for tree navigation, trace return behavior, JSON null preservation, descendant traversal, and current-function boolean/determinism probes.
- Python core `traceFn` receives projected trace values while the expression returns the original input.
- Observation only: native current-time functions emit UTC-style values while Python fallback uses local process time and preserves fractional precision. This is treated as intentional implementation policy under section 5.9.2; both backends returned valid shapes and same-expression equality.

## Evidence
- `.temp/qa/fp12_historian_probe.py`: native/fallback parity probe passed after pinning imports to the working tree.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py fhir4ds/fhirpath/tests/unit/test_new_functions.py -q --tb=short`: 72 passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration -q --tb=short`: 95 passed.
- `python3 conformance/scripts/run_fhirpath_r4.py`: report summarized as 935/935 passed.

## State
- Issues opened: 0.
- Recommended next phase: FIX with no code changes required.
