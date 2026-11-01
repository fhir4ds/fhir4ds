# Architect Handoff — CQL-01, iteration 1 (HISTORIAN), final

## Summary
QA (HISTORIAN, ~140 execution-level probes against the local CQL 1.5 spec
source) found 3 NEW divergences the SKEPTIC pass missed — all on the
numeric-semantics surface the prior pass assumed correct because spot values
(3/2=1.5) matched: (1) `/` lowered to DuckDB native division which promotes
DECIMAL to DOUBLE — even the spec's own example 9.9/3.0 returned
3.3000000000000003; (2) list Sum computed through a DOUBLE list_transform —
Sum({0.1,0.2})=0.30000000000000004 and Sum({maximum Long,1}) silently lost
Long precision with no overflow null; (3) Avg/Median returned DOUBLE
artifacts where CQL §20 declares Decimal. All fixed at root cause with an
exact cqlDivide UDF, native exact list sums with typed TRY_CASTs, and exact
Avg; 20 new regression tests (chunk file now 40). One recovery-gate event
(COALESCE VARCHAR×DECIMAL binder failures in 7 DQM measures) diagnosed from
generated SQL and fixed in `_translate_coalesce` type normalization — not a
blind retry.

## Structural verdict
Golden standard: .temp/architect/golden_standard_cql01_historian.md.
Compliant: no layering violations, no SQLRaw, no fixture hacks; the Tier-3
UDF is justified (exact base-10 division is inexpressible in DuckDB SQL) and
self-nulling per the volatile-UDF/TRY doctrine. Residual (documented, LOW):
median/stddev family quantize DOUBLE computations to DECIMAL(38,8) — exact
Decimal list median/stddev is net-new DuckDB capability; flagged for a
future chunk, not this one.

## QA enforcement gate
QA was thorough: exhaustive spec-section walkthrough (escape tables,
Table 9-E/9-G, To* formats, extents, aggregates), re-verified all 6 SKEPTIC
fixes live, and disproved harness-artifact candidates before filing. No
RETRY_QA.

## Exit
Iteration 1 >= min_iterations (1); zero non-terminal CRITICAL/HIGH/MEDIUM
issues. exit_reason CLEAN. Baseline 2832/2832 held (ViewDef 144, FHIRPath
935, CQL 1706, DQM 47); CQL unit+integration 4906 passed / 4 skipped.
