# CQL-03 EXPLORER (launch 2) — Architect Handoff

## Summary (compressed handoff)

QA (EXPLORER) probed tz-offset DateTime arithmetic/comparisons, Date↔DateTime
and Time precision comparisons, component accessors on partials, Quantity
extremes/mixed arithmetic, Ratio accessor chaining, ToQuantity forms,
Coalesce/case/nullological matrices, Min/Max temporal list aggregates, and
calendar boundary literals on both backends; it verified the official cql.g4
grammar and CQL 1.5.3 reference text before logging. 6 issues (3 HIGH,
3 MEDIUM), all spec-cited and CONFIRMED. Remediation fixed all 6 at root
cause: temporal `.component` property accessors now route through
`dateComponent` (translator hook + standalone static type resolution);
temporal-literal define aliases inline at reference sites (mirrors CQL-02
clinical inlining); the CQL 1.5.3 combined seconds/milliseconds decimal
precision rule is implemented in BOTH the Python `_compare_at_min_precision`
and C++ `CompareTemporal` (extension rebuilt, md5
10eaecdb10d3e8fca597078fc94c999e, deployed to bundle+site-packages, cache
cleared) with the interval-boundary path exempted per the official
DateTimeIncludedInNull fixture pin; Ratio `.numerator`/`.denominator` carry
Quantity typing into arithmetic dispatch; `.timezoneOffset` parses as a
property (cql.g4 keywordIdentifier) and extracts via cqlTimezoneOffset;
`ToTime` now returns T-prefixed Time strings (canonical transport).

## Audit findings

- Golden standard: `.temp/architect/golden_standard_cql03_explorer2.md`
  (7 invariants). All changes comply: dual-engine lockstep held (QA-003 both
  engines; QA-006 Python-supplement-only, no C++ counterpart exists);
  fixture-over-prose doctrine explicitly preserved and documented at the
  interval boundary; no SQLRaw/to_sql added; binary mtime > source mtime;
  dispatch is type-driven, not test-specific.
- Observation (LOW, no action): `_static_source_cql_type` in
  `_temporal_components.py` duplicates a small subset of
  `inference.py::_infer_cql_type` because the full inference mixin lives on
  the library-level translator, not the ExpressionTranslator mixin stack
  (pre-existing architecture limitation, already noted at
  _operators.py:1162). Acceptable duplication; consolidation is a future
  refactor if it grows.
- QA ENFORCER GATE: QA was NOT lazy — spec text verified verbatim (1.5.3
  combined-decimal clause), both backends probed, boundary matrix broad.
  RETRY_QA not set.

## Verification

- `pytest fhir4ds/cql/duckdb/tests/integration` → 307 passed, 5 skipped.
- `pytest fhir4ds/cql/tests` → 4916 passed, 4 skipped.
- `conformance/scripts/run_all.py` → 2832/2832 (ViewDef 144, FHIRPath 935,
  CQL 1706, DQM 47). No regressions.

## Issue counts

SPEC_VIOLATION: 6 (3 HIGH, 3 MEDIUM) — all RESOLVED. Open issues: 0.
Recommended fix order: none remaining; chunk can close.
