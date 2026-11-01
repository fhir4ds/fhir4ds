# Architect Handoff — CQL-10 HISTORIAN, iteration 1 (2026-08-21)

Scoped structural audit of the FIX phase (see
`/mnt/d/fhir4ds/.temp/architect/golden_standard.md` for the invariant set).

## Structural health: SOUND

- **QA-001 fix architecture**: two-layer root cause (translator DOUBLE
  transport + Python UDF `float()` round-trip) fixed at both layers. The
  UDF now returns exact boundary text, matching the native extension's
  existing string contract — this *closes* a latent py↔cpp type divergence
  rather than adding one. Native binaries untouched (md5 774abbac
  verified in both repo copies); SKEPTIC fill-and-truncate semantics
  intact (re-verified by the 9/9 parity file).
- **QA-002 fix architecture**: table-driven static-type guard
  (`_ARITHMETIC_FN_STATIC_GUARDS` + `_validate_static_arithmetic_operands`)
  plus a symmetric binary-operator guard for `/ ^ * -` in `_operators.py`.
  Class-general, no fixture-specific branches; null/Any/dynamic operands
  correctly defer to runtime null semantics. The interrupted session's
  dangling call site (method undefined → AttributeError) was completed
  rather than reverted — the staged design was sound.

## Empirical validation
- Full conformance gate: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47) — no regression.
- CQL integration + unit suites: pass (WASM no-Python gate expectations
  updated to exact Decimals; `DECIMAL` added to the cast-target ignore set
  in `wasm_runtime_helpers.emitted_function_names` — cast targets are not
  catalog function lookups).
- Reproducers probe3/probe4 pass, py↔cpp byte-identical.

## QA quality gate
HISTORIAN QA was rigorous (dual-path probes, HL7 reference-implementation
verification, official-fixture citations, harness-trap documentation).
RETRY_QA = false.

## Issues
0 open. QA-001 RESOLVED, QA-002 RESOLVED (tombstoned in evolution.json,
details archived in ARCHIVE_LOG.md).

## Recommended Fix Order
None — clean exit at iteration 1 (>= min_iterations 1, zero non-terminal
CRITICAL/HIGH/MEDIUM).
