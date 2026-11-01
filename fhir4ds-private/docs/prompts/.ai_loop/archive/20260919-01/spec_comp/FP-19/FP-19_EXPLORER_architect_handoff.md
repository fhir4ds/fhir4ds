# FP-19 Architect Handoff — EXPLORER iteration 1 (2026-08-18)

## Structural health (chunk-scoped audit, golden standard in
`/mnt/d/fhir4ds/.temp/architect/golden_standard.md`)
Both fixes are general algorithms (error propagation; factor-based unit
granularity selection), not case tables. The error-message contract
(invariant 3) was honored: the new native message is in the native is_valid
acceptance list and corresponds to an already-accepted fallback class. The
extension was rebuilt (make release) and redeployed to the repo bundle and
user site-packages (invariant 6). Regression tests pin native-vs-fallback
parity for both behaviors (invariant 7).

## Issue counts
CRITICAL 0 | HIGH 1 (RESOLVED) | MEDIUM 2 (1 RESOLVED, 1 DEFERRED) | LOW 0.

## Architectural findings (logged, not fixed here)
1. ARCH-1 (MEDIUM, carried in QA-003): AGENTS.md institutional memory claims
   a native `FhirpathDerivedUnitTable()` (FP-11 note) that does not exist in
   evaluator.cpp; 86 integration-parity tests fail natively as a result
   (derived UCUM families, number±quantity add). Memory-vs-repo drift is
   itself a process risk: later launches trust the note and skip re-testing.
2. The master conformance gate (run_all.py, 2832/2832) does not execute the
   integration parity suites, so native-vs-fallback parity regressions can
   persist across launches unnoticed. Recommend the outer orchestrator
   consider adding a parity-suite gate.

## QA Enforcer Gate
QA was NOT lazy: 80+ fresh dual-engine probes across the full EXPLORER
mandate (aggregate collection/tuple building, defineVariable/%env interplay,
error mid-aggregation, lexical oddities, backtick members, $var case
sensitivity, quantity-through-aggregate), 2 real spec violations found and
reproduced with minimal cases, plus isolation of a pre-existing native gap
via the git-HEAD binary. No RETRY_QA.

## Handoff compression
QA found native swallowing incompatible-type arithmetic errors (HIGH) and
returning canonical base units for mixed-unit quantity sums (MEDIUM); the
engineer fixed both in evaluator.cpp + is_valid acceptance, rebuilt and
redeployed the extension, added 2 parity regression tests; conformance
2832/2832, fhirpath unit suites 253 + 993 passed. One MEDIUM pre-existing
native quantity-conversion gap DEFERRED as out-of-chunk (documented in
QA-003 and AGENTS.md).

## Recommended fix order (next chunk touching quantities)
1. Curated native derived-unit table mirroring nodes.py _UCUM_CONVERSIONS.
2. Compound/multi-term unit reduction in native.
3. number±quantity arithmetic branch (spec example 2 + 2 '1' // 4 '1').
4. Re-run the full integration parity suites until 0 failures.
