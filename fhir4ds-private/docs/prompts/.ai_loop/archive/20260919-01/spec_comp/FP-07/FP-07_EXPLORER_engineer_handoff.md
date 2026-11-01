# Engineer Handoff — FP-07 EXPLORER (launch 3, iteration 1, 2026-08-17)

## QA-001 (MEDIUM) — fallback temporal arithmetic re-rendered authored `Z` as `+00:00`

**Status: RESOLVED** (fix implemented, reproducer passes, focused suite green,
full conformance gate result in architect handoff).

### Reproducer (pre-fix)

- `@2020-06-30T23:59:59Z + 1 second` → native `['2020-07-01T00:00:00Z']`,
  fallback `['2020-07-01T00:00:00+00:00']`.
- Same divergence for `- 1 second`, `+ 1 minute`,
  `@2020-06-30T23:59:59.5Z + 500 milliseconds`, `+ 0 seconds` identity, and
  `.toDateTime()`-converted string operands.
- Authored `+hh:mm` offsets were already preserved by both engines; plain
  conversion and equality semantics were already correct.

### Root cause

`FP_DateTime._extractDateByPrecision`
(`fhir4ds/fhirpath/engine/nodes.py:1848-1850`) contained an explicit
normalization branch — `# Normalize Z to +00:00 for consistent output` — that
replaced the authored `Z` spelling with `+00:00` whenever arithmetic results
were rendered at hour-or-finer precision. The native evaluator (and the
§5.5.1 representation table) preserve the authored `Z`.

### Spec grounding

FHIRPath N1 §5.5.1 DateTime representation table renders UTC as `Z`; the
authored spelling survives toString and conversion in both engines, so
arithmetic must not rewrite it. No official R4 fixture pins a Z-suffixed
arithmetic output (checked `tests-fhir-r4.xml`), so the dual-engine lockstep
invariant (GLOBAL_RULES) governs: native preserve-authored-spelling is the
correct direction, matching how authored `+hh:mm` offsets already behave.

### Fix (surgical, Python-only)

`fhir4ds/fhirpath/engine/nodes.py` — the timezone suffix is now appended
verbatim (`formatted_date += timezone_str`), preserving `Z`. No native change,
no extension rebuild.

### Validation

- New regression:
  `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py::
  test_temporal_arithmetic_preserves_authored_z_suffix_parity_fp07_explorer`
  (11 cases, native vs forced fallback + exact expectations) — passes.
- `test_conversion_parity.py` full file: 41/41 pass.
- Both QA probes re-run post-fix: zero parity diffs.
- Full conformance gate: see architect handoff.

## Files changed

- `fhir4ds/fhirpath/engine/nodes.py` (1 hunk)
- `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`
  (appended regression test)
