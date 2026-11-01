# FP-13 EXPLORER Architect Handoff (2026-08-17, iteration 1)

## Golden Standard invariants audited (this chunk)
1. Dual-engine lockstep: every §6.1 semantic exists in BOTH engines with a
   native-vs-fallback parity test. ✔ Both fixes correct the native engine to
   match the already-correct Python fallback; parity tests added.
2. Extension binary hygiene: evaluator.cpp edits require rebuild + redeploy
   (repo bundle, /tmp, ~/.duckdb caches cleared). ✔ md5 bfd0ac84… consistent
   across build output, repo bundle, /tmp/duckdb_cpp_ext.
3. No spec-gaming / no case-specific hacks. ✔ Both fixes are general helpers
   (leastPrecisionDecimalPlaces; integer-exact branch in
   jsonNumbersEquivalent), no fixture-specific branching.
4. `countDecimalPlaces` trailing-zero-preserving semantics stay reserved for
   authored-precision uses (lowBoundary/highBoundary, decimal precision fn).
   ✔ Untouched; only the §6.1.2 equivalence sites moved to the
   least-precision helper.
5. Error-message contract coupling (`_is_valid_empty_result_error` ↔ native
   is_valid lists). ✔ No new execution-error messages introduced.
6. Doctrine registry respected: FP-01 calendar/UCUM fixture pins,
   offset-temperature empty, incomparable-quantity empty, NBSP
   lexical-category whitespace — all re-verified, none violated.

## QA Enforcer Gate
QA (EXPLORER) was thorough: 133 dual-path cases covering every mandated area
(iteration-criteria embedding, iif/boolean chaining, temporal precision ×
offset matrix incl. Z/+00:00/-00:00, quantity families/magnitudes/tolerance
boundaries, string whitespace classes + casefold, !=/!~ empty/error corners,
nested nulls, resource operands, full native-vs-fallback parity). Two real
HIGH bugs found + one doctrine pin; ~20 probe-expectation corrections were
properly dispositioned rather than filed. RETRY_QA: false.

## Structural health
- Issue count by category: SPEC_VIOLATION 2 (both RESOLVED), doctrine pin 1
  (INTENDED). Zero open.
- The recurring root-cause family "the same §6.1.2 precision rule lives in
  multiple native sites" struck a THIRD time (SKEPTIC: 4 plain-decimal sites;
  EXPLORER: 2 quantity sites + jsonNumbersEquivalent). The SKEPTIC ARCH-001
  deferred shared-helper recommendation is re-endorsed and slightly widened:
  extract a single precision/tolerance helper covering plain-decimal,
  quantity, and JSON-number equivalence next time evaluator.cpp's comparison
  area is touched.
- Validation: conformance 2832/2832 (baseline held), fhirpath tree 1874
  passed, probe 0 parity diffs.

## Recommended Fix Order
None required this iteration. (Deferred carry-overs unchanged: SKEPTIC
ARCH-001 shared decimal-equivalence helper; now includes the integer-exact
branch.)

## Handoff compression
qa_handoff: EXPLORER probed §6.1 across iteration functions, iif/boolean
chains, temporal precision×offset matrices, quantity tolerance boundaries,
string whitespace classes, !=/!~ empty/error corners, nested nulls, resource
operands — 133 dual-path cases; found native quantity `~` least-precision
tolerance bug (HIGH), native JSON-integer `~` binary64 merge (HIGH, found via
pytest tree during fix verification), pinned incomparable-quantity `~` EMPTY
as INTENDED. engineer_handoff: both native fixes in evaluator.cpp (new
leastPrecisionDecimalPlaces at both quantityEquivalentState sites; exact
yyjson_get_sint integer compare in jsonNumbersEquivalent), stale NBSP test
expectation updated to HISTORIAN doctrine, extension rebuilt + redeployed,
regressions in test_comparison_parity.py (16 cases) + guarded
test_equality_parity.py, 91 parity tests / 1874 fhirpath / 2832 conformance
all green.
