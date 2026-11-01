# Architect Handoff — CQL-13 (HISTORIAN), iteration 1

## Structural audit (focused on this launch's diff)
Golden-standard invariants applied: (1) dual-engine lockstep — every CQL
semantic change lands in Python fallback AND native C++ with parity tests
and a rebuilt/deployed, md5-verified extension; (2) spec-grounded
behavior; (3) no silent fallbacks / no silent no-ops; (4) Difference and
Duration must remain algorithmically distinct at EVERY precision; (5) no
test-fixture hacks; (6) unit restrictions enforced on the alias TABLE,
not per operator branch.

Findings:
- QA-001 fix is invariant-clean and, notably, CLOSES an internal
  inconsistency: day/month/year/week Difference already counted
  boundaries while sub-day precisions used duration truncation. The
  floor(epoch-ms/unit-ms) index formulation is uniform, generalizable,
  handles negative (pre-1970) epochs and timezone-aware pairs
  (UTC-normalized; mixed aware/naive stays null), and endpoint-mark
  inclusion matches the spec's own day-precision example. C++
  FloorDivInt64 exists because truncating division would silently
  reintroduce the bug for pre-1970 dates. The audit additionally caught
  that the legacy public differenceIn{Hours,Minutes,Seconds} UDFs (both
  engines) shared the defect — fixed in-loop; three stale truncation
  pins in test_datetime_udfs.py updated to boundary expectations.
- QA-002 fix is invariant-clean and completes the unit-restriction
  family: Date sub-day restriction (SKEPTIC) + Time day-level
  restriction (this launch) are now symmetric §8.1/§8.15 guards placed
  BEFORE any precision conversion, covering keyword and UCUM aliases.
- No new architecture drift. No silent fallbacks introduced. Binary
  deployment discipline verified: build/release == repo bundle ==
  site-packages md5 c08b7f98656eff298ade8b4a7379043b; no ~/.duckdb
  cache copies exist.
- QA-003 (LOW) deferred with rationale recorded: lenient null-typing
  for per-type precision keywords never produces a wrong non-null
  value; static rejection is net-new translator typing functionality.

## QA enforcement gate
QA was NOT lazy: 31 + 11 fresh dual-engine cases beyond the SKEPTIC's
178, spec re-verified against live normative text, both prior fixes
re-verified regression-free, and only high-confidence divergences filed
(2 filed, 2 reproduced, 1 LOW deferred). RETRY_QA not warranted.

## State (final)
- Issues: QA-001 (HIGH) VERIFIED, QA-002 (MEDIUM) VERIFIED, QA-003
  (LOW) DEFERRED — zero non-terminal CRITICAL/HIGH/MEDIUM issues.
- Validation: fresh full conformance 2832/2832 (ViewDef 144, FHIRPath
  935, CQL 1706, DQM 47); parity suite 17/17 (new dual-engine regression
  test); test_datetime_udfs.py 61/61 with corrected pins;
  datetime/UDF-focused run 402 passed / 5 skipped. Full-tree
  fhir4ds/cql pytest is multi-hour on this WSL/drvfs host; the
  authoritative PROC_VALIDATION gate (conformance suite) was run fresh
  and holds, and all suites touching the changed code paths passed.
- Clean exit: iteration 1 >= min_iterations 1, no open
  CRITICAL/HIGH/MEDIUM -> workflow null, exit_reason CLEAN.

## Compression (for the next agent)
HISTORIAN launch on CQL 1.5 §8.1–8.8 re-verified the SKEPTIC fixes and
found two more shared-engine defects of the same families: sub-day
Difference reused Duration truncation instead of boundary counting
(HIGH; fixed via floor boundary indices both engines + legacy UDFs +
FloorDivInt64 for pre-1970 epochs), and Time + week/day units silently
no-opped instead of null (MEDIUM; allowlist guards both engines).
Extension rebuilt/deployed (md5 c08b7f98), regression tests added,
stale pins corrected, full gate 2832/2832. LOW lenient-typing finding
deferred with rationale. Institutional memory updated in AGENTS.md and
GLOBAL_KNOWLEDGE.md.
