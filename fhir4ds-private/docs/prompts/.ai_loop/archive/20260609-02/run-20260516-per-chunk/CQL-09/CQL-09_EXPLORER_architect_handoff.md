# Architect Handoff - CQL-09 EXPLORER

Structural result: passed for the CQL-09 comparison chunk. The fixes preserve the intended layering: semantic comparison dispatch stays in `_operators.py`, public helper parity is maintained in Python and native C++ quantity surfaces, retrieve optimization remains a late SQL AST optimization without erasing typed FHIRPath semantics, and typed FHIR numeric extraction is constrained to the FHIR `value[x]` boundary rather than internal CQL tuple JSON.

Architectural invariants validated:
- `between` and ordinary comparison operators must reach semantic comparison helpers for Quantity, temporal, and dynamic FHIR operands.
- Text shape is not numeric type evidence for FHIR choice values; `fhirpath_number` is the correct typed public boundary.
- Precomputed-column optimization must not replace a typed FHIRPath call with a physically `VARCHAR` column when the typed call is carrying runtime type guards.
- Internal CQL tuple properties serialized through JSON are not FHIR resources; numeric comparisons over those properties must use safe numeric casting, not `fhirpath_number`.
- Public CQL Quantity UDF behavior must stay aligned between native-loaded and forced Python fallback DuckDB registrations.

QA quality assessment: sufficient. EXPLORER covered broad and unusual surfaces, including direct helper calls, generated population SQL, dynamic FHIR choice values, Query/Last scalar subqueries, native/fallback parity, and randomized Quantity comparisons. No retry requested.

Issue status: `QA-CQL09-EXPLORER-001` through `QA-CQL09-EXPLORER-004` are verified. No new open CRITICAL/HIGH/MEDIUM issues for this chunk.

Residual risk: none identified in this chunk after the CMS871 tuple numeric regression fix. Full conformance is back to ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822; full `fhir4ds/` pytest passed 7166 with 5 skips.
