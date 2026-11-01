# Architect Handoff — CQL-13 (SKEPTIC), iteration 1

## Structural audit (focused on this launch's diff)
Golden-standard invariants applied: (1) dual-engine lockstep — every CQL
semantic change lands in Python fallback AND native C++ with parity tests
and a rebuilt/deployed extension; (2) spec-grounded behavior — no
intuition fixes; (3) no silent fallbacks; (4) no test-fixture hacks;
(5) Difference and Duration must remain algorithmically distinct.

Findings:
- QA-001 fix is invariant-clean: Sunday-week-index arithmetic is
  generalizable (no fixture special-casing), implemented with two
  equivalent calendar computations (Python proleptic-Gregorian ordinal
  // 7; C++ Julian Day Number (jdn + 1) / 7 — cross-checked to agree for
  the full CQL 0001–9999 range, both positive so floor/int division
  agree). The architect audit additionally caught that the legacy public
  helper `differenceInWeeks` (registered DuckDB UDF) shared the same
  defect and a stale test pin — fixed in-loop with 4 corrected
  expectations; CQL conformance re-run after that change (fresh 2832/2832).
- QA-002 fix is invariant-clean: unit allowlist enforced before the
  precision-conversion step that previously absorbed invalid units as
  no-ops. Legitimate convert-and-truncate semantics for DateTime operands
  preserved (spec examples pinned).
- No new architecture drift. No silent fallbacks introduced. Binary
  deployment discipline verified: build/release md5 == repo bundle md5
  (be8c0ba575df910c4e01f8459a47b32a); no site-packages or ~/.duckdb cache
  copies exist.

## QA enforcement gate
QA was NOT lazy: 178 fresh dual-engine cases across both probe batteries
plus the pre-existing 15-test parity suite, spec verified against live
normative text before logging, and only high-confidence divergences filed
(2 filed, 2 reproduced). RETRY_QA not warranted.

## State
- Issues: QA-001 (HIGH) VERIFIED, QA-002 (MEDIUM) VERIFIED — zero
  non-terminal CRITICAL/HIGH/MEDIUM issues.
- Validation: fresh full conformance 2832/2832 (ViewDef 144, FHIRPath
  935, CQL 1706, DQM 47) run twice (after primary fixes and after the
  legacy-helper fix); pytest fhir4ds/cql 5754 passed / 9 skipped;
  parity suite 16/16; UDF tests 61/61.
- Clean exit: iteration 1 >= min_iterations 1, no open issues ->
  workflow null, exit_reason CLEAN.

## Compression (for the next agent)
SKEPTIC launch on CQL 1.5 §8.1–8.8 found the temporal stack highly
conformant except two shared-engine defects: week difference used
duration math instead of Sunday boundary counting (HIGH), and invalid
sub-day units on Date operands silently no-opped (MEDIUM). Both fixed at
root in Python + C++, extension rebuilt and md5-verified, regression
tests added (parity + UDF), full gate green. Institutional memory
updated in AGENTS.md (CQL-13 doctrine + NOT A BUG registry) and
GLOBAL_KNOWLEDGE.md (stats row + personality addendum).
