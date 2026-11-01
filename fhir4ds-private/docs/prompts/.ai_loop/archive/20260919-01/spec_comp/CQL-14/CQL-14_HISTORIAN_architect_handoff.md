# Architect Handoff — CQL-14 iteration 1 (HISTORIAN)

## Audit scope
Diff-level structural audit of the two HISTORIAN fixes against the doctrine
registry (AGENTS.md), CQL translator layering, and dual-engine lockstep.
Golden standard: .temp/architect/golden_standard_cql14_historian.md

## Findings
- QA-001 fix is at the correct layer: bound extraction belongs in the
  translator (invariant: UDFs compare points only). The no-precision branches
  now mirror the precision branches exactly; no new UDF, no SQLRaw, no
  fixture-specific branches. One fix, both engines — consistent with how the
  SKEPTIC `same as` fix was structured. OK.
- No C++ change was needed, so no extension rebuild/deploy cycle; this
  respects single-writer discipline on the native tree (sibling campaign
  sessions own it). OK.
- Architectural note (LOW, no action): native `ExtractTemporalOperand`
  (extensions/cql/src/cql_extension.cpp) still substitutes interval low for
  both operands in CompareTemporal. Unreachable from CQL after the translator
  fix, but it is a semantic trap for direct-SQL UDF callers and for any future
  translator path that passes intervals. Recommend removing interval parsing
  from the point-comparison UDFs or asserting on interval input in a future
  native-touching launch.
- QA-002 fix keeps the ValueError for genuinely wrong literal types (Time(1.5))
  while null follows the static-null convention — consistent with the
  multi-arg constructor path and the spec TimeInvalid example. OK.

## QA enforcement gate
QA was thorough: re-verified all three SKEPTIC fixes, then found a genuine
spec violation the SKEPTIC pass missed by testing INTERVAL operands of the
no-precision same-or family (SKEPTIC tested intervals only for bare `same as`
and points for everything else). Dual-engine divergence was the detection
signal. No RETRY_QA.

## Validation evidence
- Focused parity suite 21/21; temporal integration 95 passed / 5 skipped;
  fhir4ds/cql/tests 4916 passed / 4 skipped.
- Master conformance gate fresh this launch: 2832/2832 (ViewDef 144,
  FHIRPath 935, CQL 1706, DQM 47) — baseline held.

## Disposition
QA-001 RESOLVED, QA-002 RESOLVED; zero open CRITICAL/HIGH/MEDIUM;
iteration 1 >= min_iterations (1). CLEAN exit; workflow null.
