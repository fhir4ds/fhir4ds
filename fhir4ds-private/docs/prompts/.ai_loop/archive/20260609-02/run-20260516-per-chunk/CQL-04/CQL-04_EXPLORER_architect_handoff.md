# Architect Handoff - CQL-04 EXPLORER

Structural health: clean after one EXPLORER loop. The final fix is at the translator semantic boundary, not in DuckDB macro truth tables, which is the right layer for rejecting statically invalid CQL. The only architectural caveat is intentional: dynamic/unknown expressions still flow through Boolean context because the translator cannot always know runtime FHIR choice shapes statically.

Issue summary: 1 MEDIUM SPEC_VIOLATION found and resolved. No architect veto; QA covered weird compositions, null chains, temporal adjacency, query aliases, invalid operands, and native/fallback parity.

Recommended fix order: none remaining for this CQL-04 EXPLORER scope.
