# Architect Handoff - FP-12 SKEPTIC

Overall structural health: PASS.

Golden standard:
- Wrote fresh invariants to `.temp/architect/golden_standard.md` for FP-12 tree navigation, utility functions, scoped `trace()` projection behavior, per-expression clock determinism, native/fallback parity, row-resilient invalid signatures, and extension rebuild hygiene.

Audit result:
- No new architect findings.
- `QA-001` is `VERIFIED`: the implementation now matches FHIRPath §5.9 by evaluating `trace(name, projection)` per input item with `$this` and `$index`, while returning the original input collection.
- The Python fallback fix restores `$index`, vars, and chain scope in a `finally` block.
- The native C++ fix restores `index_context_`, `defined_variables_`, and `chain_defined_vars_` after success or exception.
- The fix is not hardcoded to the repro; it covers any trace projection over multi-item inputs.
- QA was sufficient for the SKEPTIC role and exercised tree navigation, trace identity/projection behavior, clock determinism, invalid signatures, and native/fallback parity. No `RETRY_QA` was set.

Issue counts:
- Found: 1
- Fixed: 1
- Verified: 1
- Open CRITICAL/HIGH/MEDIUM: 0
- Architect findings: 0

Validation reviewed:
- `python3 .temp/qa/fp12_skeptic_fresh_probe.py`
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py -q`
- `cmake --build extensions/fhirpath/build/release --config Release -j 8`
- `extensions/fhirpath/build/release/test/unittest "*fhirpath*"`
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`
- `git diff --check -- fhir4ds/fhirpath extensions/fhirpath fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp12_skeptic_fresh_probe.py`
- `python3 -m json.tool fhir4ds-private/docs/prompts/.ai_loop/evolution.json`
- Extension SHA-256 matched across build, repository, and package bundle: `9985d082e3726caf7edb9445e553baa4b3efc8c7943c514d7d21fd00b2229d3f`.

Recommended fix order:
- None for this chunk. Open review-10 findings remain tracked separately and did not intersect the FP-12 trace/tree/clock work.
