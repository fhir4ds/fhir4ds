# Architect Handoff — FP-08 evolution (iteration 1, 2026-08-17)

Structural health: SOUND. All three issues (QA-001/QA-002 MEDIUM,
QA-003 HIGH) RESOLVED with root-cause fixes in both engines; the new
§5.5.7 duration conversion table is provably scoped to the
toQuantity/convertsToQuantity path (`conv_duration_to_spec` has one
caller; native `convertQuantityUnit` has one caller, `fn_toQuantity`),
so equality/ordering/arithmetic grouping (12×30≠365 doctrine) is
untouched. Pinned calendar-vs-UCUM rejection test re-ran green.
Decimal 28-sig-digit parity is achieved with exact __int128 long
division, not a wider float mask. Extension rebuilt, dead vars removed,
redeployed to repo bundle + site-packages + ~/.duckdb caches. Verified:
new parity tests (3), duckdb suites 1564 passed, core 178 passed,
conformance 2832/2832 (baseline held). Probe suite: 137 cases, zero
parity diffs.

Issue counts: 3 found, 3 RESOLVED, 0 open, 0 deferred, 0 NEEDS_CONTEXT.
Incidental cleanup: stale Z-suffix unit expectations (2 copies) updated
to the pinned FP-07 doctrine.

QA Enforcer Gate: QA was NOT lazy (fresh dual-path probes, normative
table fetched, fixtures cross-checked). RETRY_QA = false.

Clean exit: iteration 1 ≥ min_iterations 1, zero non-terminal
CRITICAL/HIGH/MEDIUM issues. exit_reason = CLEAN.
Details archived to ARCHIVE_LOG.md.
