# QA Handoff - FP-16 EXPLORER

Scope: FHIRPath §6.4 collection operators `|`, `in`, and `contains`.

Normative basis: FHIRPath §6.4.1 says union combines two collections and eliminates duplicates by equality. §6.4.2 says `in` returns true if the singleton left operand equals any item in the right collection, returns false for singleton-in-empty, returns empty for empty left, and throws when the left operand has multiple items. §6.4.3 defines `contains` as the converse, including false for empty-left-contains-singleton, empty for empty right, and an exception when the right operand has multiple items.

Fresh probes: Created `.temp/qa/fp16_explorer_probe.py` and compared native C++ DuckDB against forced Python fallback in isolated subprocesses. The 25-case matrix covered empty operands, multi-item public wrapper resilience, numeric int/real membership, object key-order membership, nested arrays, Quantity membership/de-duplication, duplicate union behavior, and `select()` context with both `|` and `union()`.

Finding: QA-001 MEDIUM SPEC_VIOLATION. Direct/core evaluation returned empty instead of raising for `a in one` and `one contains a` when `a` had multiple items. Public DuckDB native and forced fallback both returned empty/NULL, which is expected wrapper resilience but masked the strict/core error signaling gap.

Validation during QA:
- `python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/fp16_explorer_probe.py` passed after remediation: native/fallback parity for 25 cases.
- `python3 -m pytest fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py::test_membership_operators_reject_multi_item_singleton_operand -q` passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py -q` passed: 7 tests.
