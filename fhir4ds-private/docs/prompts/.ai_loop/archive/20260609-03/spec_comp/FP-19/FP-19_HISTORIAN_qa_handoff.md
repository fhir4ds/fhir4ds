# QA Handoff - FP-19 HISTORIAN

Scope: FHIRPath N1 Section 7 Aggregates and Section 8 Lexical Elements.

Spec anchors checked from the official FHIRPath N1 release and grammar:
aggregate evaluates the aggregator once per input item with `$this`, `$index`,
and `$total`; `$total` starts as `init` or empty. Lexical whitespace is exactly
space, tab, LF, and CR. Comments are ignored outside strings/identifiers.
Grammar identifier exceptions are `as`, `contains`, `in`, and `is`; reserved
keywords such as `div`, `mod`, and duration units require delimited
identifiers. Keywords are case-sensitive.

Fresh testing performed:
- Wrote and ran `.temp/qa/fp19_historian_probe.py`.
- Compared bundled native C++ DuckDB registration against forced Python
  fallback for 31 public UDF cases and 7 direct Python core cases.
- Covered aggregate init outer focus, empty-source init, `$total`/`$index`
  restoration, comments, strict whitespace, comment delimiters inside strings
  and delimited identifiers, reserved keyword delimiters, identifier keyword
  exceptions, case sensitivity, numeric literal grammar, and no-whitespace
  calendar quantities.

Findings: no native/fallback parity mismatches and no spec violations.

Validation:
- `python3 .temp/qa/fp19_historian_probe.py`: passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_aggregate_lexical_parity.py fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py -q`: 21 passed.
- Native standalone unittest binary was not present in this checkout.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

Issues logged: 0.
