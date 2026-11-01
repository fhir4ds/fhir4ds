# Architect Handoff: CQL-19 HISTORIAN

## Golden Standard

Golden standard written to `.temp/architect/golden_standard.md`. The key invariant for this pass is that list equality, inequality, equivalence, containment, proper inclusion, distinct, and union must route element comparison through CQL semantic helpers for transported null, Quantity, clinical, interval, and temporal values, not raw SQL/DuckDB identity.

## Audit Result

Structural health is acceptable. `QA-001` is verified: the fix is centralized in the CQL list macro boundary, delegates interval-valued comparisons to the existing interval semantic helpers, and does not introduce fixture-, measure-, patient-, or implementation-guide-specific logic. Because all higher-level list operators already compose through `CQLListElementEqual` / `CQLListElementEquivalent`, the change fixes the class of interval-valued list bugs rather than one expression.

No new architectural findings were logged. QA was sufficient for the HISTORIAN role: it exercised the official list part-2 operators, direct helper surface, translated CQL, interval semantic equality, prior CQL-19 typed-null/count boundaries, and forced Python/native-loaded/no-Python registrations. `RETRY_QA` was not set.

## Verification

- `.temp/qa/cql19_historian_probe.py`: PASS.
- List Part 1 + Part 2 parity: 16/16.
- Official `CqlListOperatorsTest` parser category: 212/212.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Recommended Fix Order

No further fix order for this pass. All logged issues are terminal.
