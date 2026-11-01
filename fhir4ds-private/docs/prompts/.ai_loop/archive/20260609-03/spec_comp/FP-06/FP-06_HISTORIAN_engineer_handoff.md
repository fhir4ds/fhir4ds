# Engineer Handoff - FP-06 HISTORIAN

Resolved issues:

- `QA-001` RESOLVED: Native `iif` now enforces the §5.5.1 two-or-three argument signature and raises a spec error for multi-item input/criteria instead of returning empty or accepting extra arguments.
- `QA-002` RESOLVED: Native `toBoolean()` and `toInteger()` now reject arguments. Python fallback `toBoolean()`, `toInteger()`, and generic `convertsTo*` helpers now raise on multi-item input so constant multi-item converter expressions are invalid in `fhirpath_is_valid()` while public result UDFs remain row-resilient.

Files changed:

- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/engine/invocations/misc.py`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`
- `.temp/qa/fp06_historian_probe.py`

Validation:

- Fresh FP-06 HISTORIAN probe: `63` cases, `0` mismatches, `0` expectation failures.
- Focused parity pytest: `12 passed`.
- Native sqllogictest: `388 assertions passed`.
- Full conformance: ViewDefinition `134/134`, FHIRPath `935/935`, CQL `1706/1706`, DQM `47/47`, overall `2822/2822`.

No new issues were discovered during remediation.
