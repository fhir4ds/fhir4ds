# Engineer Handoff - FP-12 SKEPTIC

Issue handled:
- `QA-001` MEDIUM SPEC_VIOLATION is `RESOLVED`.

Root cause:
- `trace(name, projection)` treated the projection as a normal whole-collection argument in both Python fallback and native C++. Per FHIRPath §5.9, the projection is a scoped function evaluated per input item with `$this` and `$index`, and `trace()` still returns the original input collection.

Fix:
- Updated `fhir4ds/fhirpath/engine/invocations/misc.py::trace_fn` to evaluate projection per item, set `$index`, restore vars/chain/index scope, and flatten only the diagnostic projection value.
- Updated native `extensions/fhirpath/src/fhirpath/evaluator.cpp` trace dispatch to evaluate the projection per input item with `index_context_` set and scope restored.
- Added focused regression coverage in `test_tree_utility_parity.py` and `extensions/fhirpath/test/sql/fhirpath.test`.
- Rebuilt and copied `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

Validation:
- `python3 .temp/qa/fp12_skeptic_fresh_probe.py` passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py -q` passed, 10/10.
- `extensions/fhirpath/build/release/test/unittest "*fhirpath*"` passed, 894 assertions.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

No new issues were opened.
