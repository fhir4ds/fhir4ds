# Architect Handoff — CQL-01, iteration 1 (final)

## Summary
QA (SKEPTIC, execution-level probing against the local CQL 1.5 spec source)
found 6 spec divergences in the primitive-types surface; all six were fixed
at root cause with 20 focused execution-level regression tests, and the full
conformance gate held at 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706,
DQM 47). CQL unit+integration: 1801 passed / 4 skipped.

## Architectural verdict
Golden standard: see
`.temp/architect/golden_standard_cql01_skeptic.md`. No layering violations,
no silent fallbacks, no fixture-specific hacks in the fixes. Notable
structural findings:

1. **Cross-package macro clobbering (durable risk)**: FHIRPath macro
   registration runs after CQL macro registration and previously redefined
   `Truncate` with different semantics. Shared macro names must keep
   byte-identical definitions in both macro packages (now documented in
   AGENTS.md).
2. **Runner policy vs fixture text**: conformance/scripts/run_cql.py treated
   any non-NULL result for `invalid="true"` as a violation; the official
   DecimalTenthStep fixtures explicitly accept "round to a whole step". The
   relaxation is comparison-based (literal quantized to 10^-8), not a blanket
   acceptance.
3. **Volatile-function TRY constraint**: DuckDB forbids TRY() around volatile
   functions (all Python UDFs default to volatile), so overflow guards must
   stay restricted to function-call-free arithmetic.

## QA enforcement gate
QA was thorough: execution-level (not parse-only), spec-source-verified,
covered literals, promotions, conversions, extents, overflow, null
propagation, and disproved two candidate findings against the spec
(`convert 1.9 to Integer -> null` is spec-correct; `MaxValue(T)` is not CQL
grammar). No RETRY_QA.

## Exit
Iteration 1 >= min_iterations (1); zero non-terminal CRITICAL/HIGH/MEDIUM
issues. Clean exit. Pre-existing unrelated: 7 native-extension regex parity
failures in fhirpath/duckdb pytest (native path returns empty for
named-group/multiline replaceMatches) — flagged to the FP native surface
owner, outside this chunk and the conformance gate.
