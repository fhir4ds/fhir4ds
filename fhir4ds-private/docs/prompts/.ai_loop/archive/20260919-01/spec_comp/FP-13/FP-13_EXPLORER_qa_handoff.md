# FP-13 EXPLORER QA Handoff (2026-08-17, iteration 1)

Chunk: FHIRPath §6.1 Equality (=, ~, !=, !~, incl. Quantity and Date/Time
equality, String equivalence). Personality: EXPLORER (adversarial chaining /
boundary probing). Probe: `/mnt/d/fhir4ds/.temp/qa/fp13_explorer3_2026_08_17/probe.py`
(133 dual-path native-vs-forced-fallback cases, `SELECT fhirpath(?::JSON, ?)`,
PYTHONPATH=/mnt/d/fhir4ds).

## Areas probed (per mandate)
- Equality/equivalence embedded in iteration criteria over heterogeneous
  collections (where/select/repeat), incl. quantity members (cm/mm, kJ/J).
- Equality chains feeding iif and and/or/not (incl. FP-01 calendar doctrines).
- Temporal equivalence across all precision pairs and timezone-offset mixes
  (Z vs +00:00 vs -00:00 vs +01:00, minute-precision offsets crossing day
  boundaries, trailing-zero precision).
- Quantity equivalence across unit families/magnitudes (derived kJ/J/N.m,
  exponents m2/cm2, m2/m, g/s, calendar↔UCUM, kg/g/mg spans, tolerance
  boundaries, offset temperature INTENDED-empty re-verified).
- String equivalence: mixed whitespace classes (tab/LF/CR/space per the
  HISTORIAN lexical-category fix; NBSP correctly NOT normalized), casefold
  (ß/SS), no collapsing.
- != / !~ on empty/error/error-typed operands in both positions.
- Deeply nested complex objects and arrays with JSON nulls; resource-type
  operands; resource fields driving all four operators.
- Native-vs-fallback parity on every case.

## Findings
- QA-001 (HIGH, OPEN→fix): native Quantity `~` tolerance used
  trailing-zero-preserving precision — `1.0 'g' ~ 1.06 'g'` native false vs
  fallback true (precision 0 half-width 0.5). Same family as SKEPTIC QA-001
  (plain decimals) but on the quantityEquivalentState sites; contaminates
  `!~` and iif criteria.
- QA-002 (HIGH, found during fix verification via the fhirpath pytest tree):
  native `~` on JSON integers > 2^53 coerced through binary64
  (`9007199254740992 ~ 9007199254740993` → true; `=` correctly false).
- QA-003 (LOW INTENDED): `1 'cm' ~ 1 's'` EMPTY in both engines — pinned to
  the incomparable-quantity doctrine; do not "fix".

## Not-a-bug confirmations (probe-expectation corrections)
Union `|` dedups via `=` at construction ((1|1.0) collapses; quantity unions
dedup cross-unit); `given = 'John'` on 2-element collection false (§6.1 count
mismatch); iif with empty criterion takes else-branch; `{} != {}` empty (§6
pinned); trailing-zero fractional seconds equal (`@T00:00:00.0 ~
@T00:00:00.00` true); `1e9 'mg'` exponent quantity literals evaluate empty in
both engines (exotic-literal doctrine); `resourceType = 'Patient'` true.

Zero parity diffs remain after the two fixes; conformance 2832/2832 held.
