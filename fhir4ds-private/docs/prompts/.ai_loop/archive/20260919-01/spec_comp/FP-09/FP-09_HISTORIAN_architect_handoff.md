# Architect Handoff — FP-09 HISTORIAN (iteration 1, 2026-08-17)

## Golden-standard check
Invariant applied: "Exported direct helpers in
`fhir4ds/fhirpath/duckdb/functions/` are public compatibility surface and
must mirror engine (core + native) semantics for empty collections,
argument typing, and boundary rules" (established FP-09/FP-11 HISTORIAN,
FP-04 EXPLORER, FP-08 HISTORIAN doctrine). The QA-001 fix satisfies it:
typed errors, no silent fallbacks, no case-specific hardcoding, minimal
footprint (one module + one test class), engine parity verified
empirically.

## Findings
- No architecture drift introduced. No new invariants needed beyond the
  existing direct-helper doctrine; the recurring root cause ("exported
  helper API forgotten", now 4 instances: FP-04 filter.py, FP-08
  conversion.py, FP-09 string.py index_of, FP-09 string.py argument
  contract) is already logged in AGENTS.md as a fragile-area pattern.
- Convention correction landed in AGENTS.md: negative substring LENGTH →
  `''` (both engines), only negative START → `{}`; the SKEPTIC-era pin
  conflated them.

## QA Enforcer Gate
QA quality sufficient: fresh HISTORIAN angles (sourced-call argument
focus, astral-plane code points, length sign matrix, is_valid parity),
SKEPTIC fix re-verified, one real MEDIUM found and fixed. RETRY_QA =
false.

## State hygiene
- QA-001 evidence archived to ARCHIVE_LOG.md; issue tombstoned
  RESOLVED/VERIFIED in evolution.json.
- Exit: iteration 1 ≥ min_iterations 1; zero non-terminal
  CRITICAL/HIGH/MEDIUM → CLEAN exit.

## Summary
One-paragraph compression: HISTORIAN rerun of §5.6.1–§5.6.5 confirmed
native/Python-fallback engine parity across ~60 fresh dual-path checks
and re-verified the SKEPTIC index_of fix; one MEDIUM direct-helper
engine-contract gap (empty/non-String argument TypeErrors, negative
length → {} instead of '') was fixed in
`fhir4ds/fhirpath/duckdb/functions/string.py` with 10 regression cases;
fhirpath tree 1767 passed; conformance 2832/2832 held.
