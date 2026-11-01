# Architect Handoff — CQL-03 HISTORIAN

## Golden Standard

Updated `.temp/architect/golden_standard.md` for CQL-03 temporal/complex type
boundaries. The added invariant is that DateTime constructor
`timezoneOffset` lowering must be type-aware: static offsets are Decimal hours,
must serialize as valid ISO `(+|-)hh:mm`, and must not rely on Boolean/string
coercion.

## Structural Audit

No new architectural issues were found.

The fix is appropriately scoped to
`fhir4ds/cql/translator/expressions/_temporal_components.py`, where CQL
DateTime constructor lowering belongs. It preserves the parser/translator/SQL
layering, uses SQL AST nodes rather than mid-pipeline raw SQL, and keeps
runtime constructor output guarded by the existing temporal parser validation.
No C++ extension change was needed because the defect was in translated CQL
SQL generation.

## QA Quality

QA was adequate for HISTORIAN: it tested public helper surfaces, translated CQL
execution, constructor precision, invalid static constructor types, and
native-loaded versus forced Python fallback parity. No `RETRY_QA` veto is set.

## Issue Summary

- `QA-001` HIGH `SPEC_VIOLATION`: resolved and verified.
- New architect findings: 0.

## Validation Evidence

- `.temp/qa/cql03_historian_probe.py`: passed.
- Focused pytest temporal/conversion/Ratio set: 53 passed.
- Focused temporal subset after cleanup: 6 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

Recommended next step: outer spec-compliance orchestrator should archive this
HISTORIAN pass and launch CQL-03 EXPLORER.
