# Architect Handoff — CQL-10 SKEPTIC iteration 1 (2026-08-21)

## Audit summary

Structural audit of the CQL-10 fixes against the loop's architectural
invariants:

- **Dual-path lockstep (GLOBAL_RULES)**: SATISFIED. High/LowBoundary Decimal
  semantics and mathCeiling/mathFloor Integer-extent guards implemented in BOTH
  the Python UDF layer (`fhir4ds/cql/duckdb/udf/math.py`) and the C++ extension
  (`extensions/cql/src/cql/boundary.cpp`, `math.cpp`), with native-vs-fallback
  parity assertions added in the regression test. Cross-path spot verification
  of all five fixes on fresh connections: ALL-PARITY-OK.
- **Extension deployment (GLOBAL_RULES)**: SATISFIED. Extension rebuilt
  (cmake --build release), binary mtime > source mtime, md5
  `774abbac349f6e6a755f7317ba4a4978` matched across build output, repo bundle
  (`fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`), and site-packages;
  `~/.duckdb/extensions/*` cache dirs are empty (no stale-binary hazard); fix
  re-verified through a reloaded C++ connection.
- **No SQLRaw / no silent fallbacks**: The fixes use typed `TRY_CAST`
  narrowing whose NULL-on-overflow is the spec-mandated behavior, not a mask.
- **Generalizability**: The boundary helper is a general fill-and-truncate
  algorithm; the Integer→Long promotion keys on statically inferred operand
  types (not values); Abs typed narrowing applies to any statically integral
  arithmetic tree. No test-specific special cases added.
- **Doctrine conflict resolved correctly**: v2 spec prose example
  `HighBoundary(1.587,2)//1.59` conflicts with the HL7 reference
  implementation (1.58). Engineer followed the fixtures/reference-outrank-prose
  doctrine and mirrored the reference. Documented in fhir4ds/cql/AGENTS.md.

## Empirical validation

- Full conformance: **2832/2832** (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47)
  — exact baseline hold.
- Full `pytest fhir4ds/cql` tree: **5738 passed, 9 skipped (environment), 0
  failed**.
- Focused regression: 8/8 in test_arithmetic_operator_parity.py (new test
  `test_cql_arithmetic_spec_compliance_boundaries_typing_and_promotion`).

## QA quality gate

QA phase was strong: 5 genuine spec violations found via hypothesis-driven
probing on both backends, each grounded in spec text and the HL7 reference
implementation, with reproducers preserved. NOT A BUG confirmations recorded.
No RETRY_QA.

## Issue disposition (all terminal)

| ID | Severity | Status |
|---|---|---|
| QA-001 High/LowBoundary Decimal precision semantics | HIGH | VERIFIED (iter 1) |
| QA-002 Ceiling/Floor Integer-extent null rule | HIGH | VERIFIED (iter 1) |
| QA-003 Integer+Long Add promotion → runtime error | HIGH | VERIFIED (iter 1) |
| QA-004 Abs typed-overflow guard too narrow | MEDIUM | RESOLVED→VERIFIED (iter 1) |
| QA-005 Exp/Ln/Log return DOUBLE not Decimal | MEDIUM | VERIFIED (iter 1) |

Zero non-terminal CRITICAL/HIGH/MEDIUM issues remain and iteration 1 >=
min_iterations (1) → clean exit.

## Recommended fix order (future)

None for this chunk. Residual note: the four literal-shape Abs guards in
`_functions.py` Step 2b are now largely redundant with the typed narrowing
(except they preserve the exact `NULL` SQL emission asserted by
`test_primitive_parity`); leave in place, documented.
