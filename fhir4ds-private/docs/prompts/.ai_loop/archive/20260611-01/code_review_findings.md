# Code Review Findings

## Reviewed Scope

- `fhir4ds/cql/translator/expressions/_utils.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/translator/expressions/_query.py`
- `fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py`
- `fhir4ds/dqm/tests/unit/test_evaluator.py`
- `fhir4ds/cql/AGENTS.md`
- Remediation state/handoff files in `fhir4ds-private/docs/prompts/.ai_loop/`

Pre-existing unrelated working-tree changes in `conformance/reports/dqm_report.json`, website docs/sidebar files, and untracked CQL tests runner facade artifacts were not reviewed as part of this targeted code review.

## Findings

No CRITICAL, HIGH, MEDIUM, or LOW findings.

## Review Notes

- Named type recognition now uses generated FHIR R4 type metadata instead of extending the prior hand-maintained named-type allowlist for each datatype.
- Dynamic FHIR datatype assertions avoid generic `resourceType` probing for direct FHIRPath values and use `type().name` as the primary runtime guard.
- The native fallback is intentionally narrow: it applies only to `Coding` when native FHIRPath reports an ambiguous complex container such as `BackboneElement`, and it is gated by that ambiguous type report. JSON-looking string transport values remain rejected.
- Added regression coverage exercises translation acceptance, invalid target rejection, strict cast preservation, DQM compilation, and Python/native runtime parity for `FHIR.Coding`.

## Validation Reviewed

- Final touched suites: `55 passed, 2 warnings`.
- Final conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- Final full pytest: 7925 passed, 7 skipped, 9 warnings.
