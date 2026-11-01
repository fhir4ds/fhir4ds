# QA Handoff: FP-05 HISTORIAN

## Scope

- Chunk: FP-05
- Personality: HISTORIAN
- Spec focus: FHIRPath Normative Release v2.0.0 sections 5.3 Subsetting and 5.4 Combining
- Spec source: https://hl7.org/fhirpath/N1/

## Spec Grounding

FHIRPath collections are ordered, non-unique, indexed from 0 unless the model says otherwise, and countable. Section 5.3 defines `[index]`, `single()`, `first()`, `last()`, `tail()`, `skip(num)`, `take(num)`, `intersect(other)`, and `exclude(other)`. Section 5.4 defines `union(other)`/`|` and `combine(other)`. The probe asserted the documented empty-boundary behavior, duplicate handling, and equality-backed set semantics:

- `single()` returns the item only for one-item input and signals an execution error for multi-item input; public DuckDB wrappers return empty/NULL for row resilience.
- `skip(num)` returns the original input for `num <= 0`; `take(num)` returns empty for `num <= 0`.
- `intersect()` and `union()` eliminate duplicates using FHIRPath equality.
- `exclude()` preserves input order and does not eliminate input duplicates that remain.
- `combine()` preserves duplicates.

## Probe

Created a fresh subprocess-isolated probe:

- `.temp/qa/fp05_historian_probe.py`
- `.temp/qa/fp05_historian_probe_after_expectation_fix.log`

Coverage: 53 cases across native C++ DuckDB registration and forced Python fallback registration, comparing all public wrapper outputs (`fhirpath`, `fhirpath_json`, `fhirpath_text`, `fhirpath_number`, `fhirpath_bool`, `fhirpath_is_valid`) and asserting section-level collection/JSON/validity expectations.

Result: `failure_count=0`.

## Validation

- Focused parity pytest: `fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py` -> 8 passed.
- Native extension sqllogictest: `extensions/fhirpath/build/release/test/unittest '*fhirpath*'` -> 366 assertions passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Issues

No issues logged. No remediation required.
