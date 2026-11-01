# Engineer Handoff — FP-09 HISTORIAN (iteration 1, 2026-08-17)

## QA-001 (MEDIUM, RESOLVED) — direct string helper engine-contract gaps

Reproducer (pre-fix): `starts_with(FHIRPathCollection(['hello']), None)`
→ raw `TypeError`; `substring(FHIRPathCollection(['hello']), 1, -2)` →
`FHIRPathCollection([])` while both engines return `''`.

Root cause: `fhir4ds/fhirpath/duckdb/functions/string.py` direct helpers
predate the direct-helper doctrine — they assumed Python `str` args and
never implemented the engine contract for empty argument collections,
non-String arguments, or the negative-length substring rule (§5.6.2:
engines return the empty string for length <= 0; native `fn_substring`
len<=0 → `{""}`, core `strings.substring` length<=0 → `""`).

Fix (Python-only; native and core engine unchanged, no rebuild):
- Added `_validate_string_arg(value, func, arg)`: `None` → the caller
  returns an empty collection (engine "empty argument" semantics);
  non-`str` → `FHIRPathFunctionError` (typed error, not raw TypeError).
- Applied in `starts_with`, `ends_with`, `contains`.
- `substring`: `start is None` → empty collection; `length_val <= 0` →
  `''` (matches both engines), replacing the old `< 0 → {}` divergence.

Regression coverage:
`TestStringHelperEngineContractFp09Historian` (10 cases) in
`fhir4ds/fhirpath/duckdb/tests/unit/test_string.py`.

## Validation (Recovery Gate)
- Probe re-run: helper matrix aligned with engines; zero engine parity
  diffs (`.temp/qa/fp09_historian2_2026_08_17/probe.py`).
- `pytest fhir4ds/fhirpath` → 1767 passed.
- Full conformance `run_all.py` → FHIRPath 935, CQL 1706, ViewDef 144,
  DQM 47 = 2832/2832 (baseline held).

No other issues opened; no DEFERRED / NEEDS_CONTEXT items.
