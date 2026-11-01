# Architect Handoff — CQL-05 EXPLORER iteration 1 (2026-08-20)

## Summary

EXPLORER QA found 3 real spec violations in the CQL structural type-operator
chunk family (all silent wrong results or non-executable SQL on both native and
Python paths): QA-104 strict-cast-in-arithmetic TRY/volatile binder error,
QA-105 element access over retrieve-bound define aliases, QA-106 array/backbone
property access on singleton resource expressions. Remediation fixed all three
with consumer-site, metadata-driven changes after one recovery-gate iteration
(an initial generic LIST-usage aggregation in `_core.py` regressed DQM 47→28 and
was reverted for localized fixes). One out-of-chunk discovery (QA-107,
list-literal query sources misclassified PATIENT_SCALAR) is DEFERRED with a
recommended follow-up chunk. Gate verified 2832/2832; structural parity tests
22/22 including three new regression tests.

## Structural health

- Golden standard for this scope: `/mnt/d/fhir4ds/.temp/architect/golden_standard_cql05_explorer_2026_08_20.md`.
  All three fixes pass the invariants (type-driven, no silent fallbacks,
  consumer-site coercion, native/python parity).
- Drift note: element-list materialization now exists in three helpers
  (`_translate_first_last_over_retrieve`, `_translate_first_last_over_cte`,
  `_definition_resource_rows_list`) — reinforce the existing Drift Log item:
  converge on one list-source path when the `_translate_query` consolidation
  lands.
- Issue counts this iteration: 3 RESOLVED (1 HIGH + 1 HIGH + 1 MEDIUM), 1
  DEFERRED (MEDIUM, out-of-chunk). 0 CRITICAL. No RETRY_QA (QA coverage was
  adversarial and dual-path).

## Recommended fix order (next chunk)

1. QA-107 (deferred): row-shape classification for list-typed query defines in
   `_translate_query`/definition-meta inference — converge with the Drift Log
   consolidation rather than per-shape patches.
2. Forward-reference detection for RESOURCE_ROWS defines (`definition_meta`
   order dependency) — small, follows the QA-105 fix pattern.

## State hygiene

Resolved-issue details archived to ARCHIVE_LOG.md; evolution.json carries
tombstones. Completion state: workflow=null, exit_reason=CLEAN (iteration 1 ≥
min_iterations=1, zero non-terminal CRITICAL/HIGH/MEDIUM).
