# Engineer Handoff - FP-08 SKEPTIC

Issue status:
- `QA-001` MEDIUM `RESOLVED`

Root cause:
- Native C++ `Evaluator::evalFunction()` evaluated the optional `unit` argument for `toQuantity([unit])` and `convertsToQuantity([unit])` against the sourced Quantity/String input.
- For expressions like `value.toQuantity(targetUnit)` and `items.select(quantityText.toQuantity(targetUnit))`, this made sibling unit paths resolve empty in native DuckDB while forced Python fallback resolved them from the outer invocation context.

Fix:
- Updated native `toQuantity()` and `convertsToQuantity()` dispatch in `extensions/fhirpath/src/fhirpath/evaluator.cpp` to evaluate the optional unit expression against `outer_input` when available, falling back to `input` otherwise.
- Added dynamic-unit parity coverage in `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`.
- Added native sqllogictest coverage in `extensions/fhirpath/test/sql/fhirpath.test`.
- Rebuilt and copied `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.
- Corrected `.temp/qa/fp08_skeptic_fresh_probe.py` to prepend the repo root to `sys.path`; launching scripts under `.temp/qa` otherwise imports installed site-packages `fhir4ds`.

Deep research:
- Appended `QA-001` to `fhir4ds-private/docs/prompts/.ai_loop/state/deep_research_findings.md`.

Validation:
- `python3 .temp/qa/fp08_skeptic_fresh_probe.py` passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_fp08_empty_quantity_unit_parity.py -q` passed, 22/22.
- `cmake --build extensions/fhirpath/build/release --config Release -j 8` passed.
- `extensions/fhirpath/build/release/test/unittest "*fhirpath*"` passed, 794 assertions.
- Extension hashes match across build, repository, and package bundle.
- `git diff --check -- ...` passed.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

New issues discovered:
- None.
