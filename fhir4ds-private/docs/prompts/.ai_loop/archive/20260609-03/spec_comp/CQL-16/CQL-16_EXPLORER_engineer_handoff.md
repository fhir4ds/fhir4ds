# Engineer Handoff - CQL-16 EXPLORER

## Scope
CQL-16 Interval Operators Part 2, EXPLORER personality, iteration 1. The run used fresh probes only; quarantined CQL-16 misfire artifacts were not used as evidence. `docs/architecture/translator/AGENTS.md` was not present, so root `AGENTS.md`, `extensions/cql/AGENTS.md`, durable knowledge, and the role/procedure prompts governed the pass.

## Issue Resolved
- `QA-001` HIGH `SPEC_VIOLATION`: translated dynamic FHIR partial temporal point values bypassed precision uncertainty. `Observation.effectiveDateTime: "2014"` evaluated `O.effective overlaps day of Interval[@2014-06-01, @2014-06-02]` as `false`; the equivalent partial interval expression is unknown and should return SQL NULL.

## Root Cause
Precision-qualified translated `overlaps`, `overlaps before`, and `overlaps after` used the DQM-optimized decomposed start/end SQL path. That path correctly handles concrete Period intervals, but it did not detect runtime scalar Date/DateTime values whose precision is lower than the requested precision. A first broad guard also showed why this path cannot be replaced or guarded wholesale: CMS135 active allergy intervals have partial starts and null high endpoints, and those must continue evaluating as active unbounded intervals.

## Resolution
`fhir4ds/cql/translator/expressions/_operators.py` now wraps precision-qualified decomposed overlap predicates with a narrow runtime temporal precision guard. The guard counts temporal digits after stripping timezone suffixes and returns SQL NULL only when a present runtime bound is under-precise and has a finite paired endpoint. It extracts raw low/high peers from `SQLInterval`, `intervalFromBounds(...)`, and CASE-wrapped interval expressions, so active unbounded intervals with null high endpoints are not nulled by their partial start. Directional precision overlaps now compute the base overlap from the same decomposed comparisons instead of calling `intervalOverlaps(...)`, preserving no-Python/native extension parity for dynamic Period values.

## Validation
- `PYTHONPATH=. python3 .temp/qa/cql16_explorer_probe.py`: passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_interval_part2_parity.py -q`: 6 passed.
- CMS135 targeted DQM run: 100.0%, no mismatched patients.
- `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_interval_operators -q`: 412 passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_interval_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_interval_part3_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py -q`: 28 passed.
- `python3 conformance/scripts/run_all.py`: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Notes for Architect
The fix is structural, not fixture-specific. It introduces generic SQL AST helpers for interval low/high peer extraction and keeps the optimized DQM overlap decomposition intact. Durable knowledge and root/CQL AGENTS notes were updated with the raw-peer/unbounded-interval guardrail.
