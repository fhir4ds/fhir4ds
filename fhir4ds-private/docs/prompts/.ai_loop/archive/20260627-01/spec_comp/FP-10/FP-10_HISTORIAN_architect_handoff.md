# Architect Handoff - FP-10 HISTORIAN

Date: 2026-06-12

## Structural Health

The FP-10 HISTORIAN fix is structurally sound. QA exercised the full
§5.6.6-§5.6.12 transform boundary against native DuckDB/C++ and forced Python
fallback paths, found a real Unicode case-conversion gap, and remediation
localized the fix to native string case mapping without changing public
signatures or row-resilience behavior.

Golden standard: `.temp/architect/golden_standard.md`.

## Audit Result

- New architect findings: 0
- `RETRY_QA`: false / not set
- Open CRITICAL/HIGH/MEDIUM issues: 0
- `QA-001`: VERIFIED

The native fix delegates one-to-one Unicode case mapping to DuckDB's vendored
`utf8proc` and keeps the remaining full-case uppercase expansions as a narrow
data-only table. That satisfies the core architecture requirement to avoid
behavior-changing ad hoc range logic while preserving FHIRPath's Unicode scalar
semantics. Permanent coverage exists in both the Python native/fallback parity
tests and native sqllogictest assertions, and the bundled extension was
rebuilt with matching hashes.

## QA Audit

QA was sufficient for the HISTORIAN role. It started from the current HL7
FHIRPath spec text, covered every function in the chunk, included dynamic
arguments, invalid flags/signatures, Unicode scalar `replace()` / `length()` /
`toChars()` behavior, and specifically challenged native/fallback parity.
No retry is needed.

## Validation Confirmed

Architect validation re-ran:

```bash
python3 .temp/qa/fp10_historian_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py -q
git diff --check -- extensions/fhirpath/src/fhirpath/evaluator.cpp extensions/fhirpath/test/sql/fhirpath.test fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py fhir4ds/fhirpath/AGENTS.md extensions/fhirpath/AGENTS.md fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp10_historian_fresh_probe.py .temp/architect/golden_standard.md
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
```

Results:

- Fresh probe passed: 29 expressions.
- Focused transform parity passed: 4/4.
- Diff check passed.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL
  1706/1706, DQM 47/47, overall 2822/2822.

## Recommended Fix Order

No further fix phase is required for this launch. Remaining milestone review
findings `REV-FP-002` and `REV-FP-003` remain outside FP-10 HISTORIAN unless
the outer orchestrator schedules them explicitly.
