# Architect Handoff - FP-09 EXPLORER

## Structural Health

The FP-09 EXPLORER fix is architecturally sound. The defect was isolated to the Python fallback implementation of `substring()`, while native C++ already matched HL7 FHIRPath §5.6.2. The remediation changed only the incorrect fallback branch, preserved existing empty-input and out-of-range-start semantics, and added both literal and dynamic native/fallback parity coverage.

## Golden Standard

Wrote `.temp/architect/golden_standard.md` with 10 FP-09 invariants covering spec-first semantics, Unicode scalar-value positions, native/fallback parity, expression-validity separation, dynamic argument focus, empty search-term behavior, and the specific `substring` distinction between out-of-range `start` and in-range `length <= 0`.

## QA Audit

QA was sufficient for the EXPLORER role. The fresh probe covered Unicode scalar-value boundaries, empty search terms, dynamic sibling-field arguments inside and outside `select()`, runtime type/cardinality row resilience, and negative `substring` lengths beyond the existing coverage. No `RETRY_QA` veto was set.

## Findings

- `QA-001` MEDIUM SPEC_VIOLATION: VERIFIED. Python fallback `substring(start, length)` leaked Python negative-slice semantics for sufficiently negative `length`, returning content instead of the §5.6.2-required empty string.
- New architect findings: 0.
- Open CRITICAL/HIGH/MEDIUM issues from this loop: 0.

## Validation

```bash
python3 .temp/qa/fp09_explorer_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py -q
git diff --check -- fhir4ds/fhirpath/engine/invocations/strings.py fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py fhir4ds/fhirpath/AGENTS.md extensions/fhirpath/AGENTS.md fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp09_explorer_fresh_probe.py .temp/architect/golden_standard.md
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
```

Results:
- Fresh probe passed, 46 expressions.
- Focused parity passed, 6/6.
- Diff check passed.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Recommended Fix Order

No further engineer work is required for FP-09 EXPLORER. Milestone review findings `REV-FP-002` and `REV-FP-003` remain open outside this chunk and did not intersect the §5.6.1-§5.6.5 search-function fix.
