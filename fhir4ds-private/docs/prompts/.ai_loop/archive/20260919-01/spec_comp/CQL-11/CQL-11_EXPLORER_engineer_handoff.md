# Engineer Handoff — CQL-11 EXPLORER2 (2026-08-21)

All four QA issues fixed at root cause; no workarounds; no native rebuild needed (all fixes are Python-fallback or translator-level, keeping dual-engine parity).

## Fixes
- QA-001 (HIGH) RESOLVED/VERIFIED — `fhir4ds/cql/translator/expressions/_operators.py`: `_infer_static_numeric_type` now infers through `Coalesce(...)` (list and arg forms); `successor of` / `predecessor of` emit a `CASE WHEN operand >= maximum Integer THEN NULL ELSE successorOf(...) END` guard for statically Integer-typed non-literal operands. Spec: CQL 1.5 App. B Arithmetic intro + Successor/Predecessor ("overflow ... result is null"). Long operands keep the plain helper (BIGINT overload nulls at int64 bounds).
- QA-002 (HIGH) RESOLVED/VERIFIED — `_operators.py` unary `-`: operands lowering to `cqlDurationBetween`/`cqlDifferenceBetween` (Integer-valued in CQL, VARCHAR in SQL) are wrapped in `TRY_CAST(... AS BIGINT)` before prefix minus. Fixes binder error `-(VARCHAR)` for `-(days between A and B)`.
- QA-003 (MEDIUM) RESOLVED/VERIFIED — `fhir4ds/cql/duckdb/udf/quantity.py` `quantityNegate`: removed pint round-trip; negates the value and re-serializes preserving unit/code/system verbatim with native JSON key order. Fixes `-(3 days)` py 'day' vs cpp 'd' divergence.
- QA-004 (LOW) RESOLVED/VERIFIED — `fhir4ds/cql/parser/parser.py` `parse_expression`: raises `ParseError` on trailing tokens instead of silently parsing a prefix.

## Regression tests
`fhir4ds/cql/duckdb/tests/integration/test_arithmetic_part2_parity.py`: 4 new `*_cql11_explorer2` tests (dual-engine parity + spec expectations). All pass.

## Validation
- Focused: 4/4 new tests pass.
- `python3 -m pytest fhir4ds/cql -q`: 5749 passed, 9 skipped.
- `conformance/scripts/run_all.py`: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2832/2832 — baseline holds.

No new issues discovered during remediation.
