# QA Handoff — Iteration 1 (SKEPTIC)

**Personality**: SKEPTIC
**Focus**: Domain 4 — CQL: Real-World eCQM Patterns
**Date**: 2026-05-05

## Summary

Conducted adversarial review of the CQL/DQM subsystem focusing on eCQM measure evaluation patterns. Explored the full pipeline: CQL parsing → SQL translation → DuckDB execution → population counting. Created 79 C++/Python parity tests (77 pass, 2 fail). Ran full conformance baseline (2816/2821 = 99.8%).

## Issues Found (6 total: 3 HIGH, 2 MEDIUM, 1 LOW)

### HIGH
1. **QA-001**: C++ `YearsBetween` off-by-one — uses raw `end.year - start.year` instead of counting complete calendar periods. Test: `YearsBetween('1980-06-15', '2024-06-14')` → 44 (C++, wrong) vs 43 (Python, correct). File: `extensions/cql/src/cql_extension.cpp:333-335`.
2. **QA-002**: C++ `MonthsBetween` edge case — returns 12 instead of 11 for boundary dates. Same root cause class as QA-001. Test: `MonthsBetween('2023-06-16', '2024-06-15')` → 12 (C++, wrong) vs 11 (Python, correct).
3. **QA-003**: Fix scripts target wrong directory/format. `fix_bundles.py` fixes `bundles/measure/` but runner reads `input/tests/measure/`. `fix_upstream_data.py` targets directory-format files but loader uses bundle-format files. CMS135/CMS145 remain unfixable by either script.

### MEDIUM
4. **QA-004**: Unit test regression — `test_and_preserves_trace` in audit macros failing.
5. **QA-005**: `population_basis` parsed but never propagated to translator (latent — no current measures affected).

### LOW
6. **QA-006**: C++ quantity serialization uses float (`140.0`) vs Python int (`140`). Cosmetic only.

## Conformance Baseline

| Suite | Passed | Total | Rate |
|-------|--------|-------|------|
| ViewDefinition | 134 | 134 | 100.0% |
| FHIRPath (R4) | 935 | 935 | 100.0% |
| CQL | 1706 | 1706 | 100.0% |
| DQM | 41 | 46 | 89.1% |
| **OVERALL** | **2816** | **2821** | **99.8%** |

Unit tests: 61 passed, 1 failed, 5 skipped.

## Key Code Areas Probed

- `fhir4ds/cql/translator/translator.py` — CQL→SQL pipeline
- `fhir4ds/cql/translator/expressions/_query.py` — with/such-that handling
- `fhir4ds/cql/translator/expressions/_operators.py` — in_valueset dispatch
- `fhir4ds/dqm/parser.py` — Measure parsing, population_basis extraction
- `fhir4ds/dqm/evaluator.py` — Group evaluation, population counting
- `fhir4ds/cql/duckdb/udf/valueset.py` — valueset membership UDF
- `extensions/cql/src/cql_extension.cpp` — C++ extension function registration

## Test Artifacts

- `.temp/qa/test_cpp_vs_python.py` — 79 C++/Python parity tests
