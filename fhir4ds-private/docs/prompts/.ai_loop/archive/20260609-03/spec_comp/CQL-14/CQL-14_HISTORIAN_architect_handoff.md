# Architect Handoff: CQL-14 HISTORIAN

## Golden Standard

Wrote `.temp/architect/golden_standard.md` with CQL-14 temporal invariants:
precision-preserving constructors, uncertainty-aware temporal comparison
helpers, CQL-shaped current-clock outputs, shared Date/Time quantity arithmetic
surfaces, AST-based translator SQL generation, and native/Python/no-Python
parity coverage.

## Audit Result

No new architectural findings were logged.

`QA-001` is structurally acceptable after remediation. The change is localized
to `fhir4ds/cql/translator/expressions/_temporal_components.py`, keeps Time
constructor precision selection in the translator layer, uses SQL AST nodes
rather than mid-pipeline raw SQL, and adds no profile-, measure-, or
fixture-specific branches. The checked-in regression lives next to adjacent
Date/Time Part 2 parity tests and the fresh probe exercises forced Python
fallback, native-loaded registration, and no-Python C++ helper surfaces where
available.

## QA Audit

QA was sufficient for HISTORIAN scope. It covered official Date/Time Part 2
semantics, current-clock shape/stability, timezone-normalized precision
helpers, invalid precision, Date/DateTime/Time minus Quantity, one-argument
`Time(hour)` vs `time from <DateTime>`, trailing-null Time constructor
precision, malformed Quantity rejection, and full conformance. No `RETRY_QA`
flag is needed.

## Validation

- Fresh probe: PASS.
- Focused Date/Time Part 2 plus no-Python/WASM C++ pytest: 10/10.
- Official DateTime operator category: 246/246.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

## Recommended Fix Order

No remaining CQL-14 HISTORIAN fixes.

