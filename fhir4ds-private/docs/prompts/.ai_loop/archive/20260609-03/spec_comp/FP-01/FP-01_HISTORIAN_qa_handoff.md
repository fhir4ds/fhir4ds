# QA Handoff - FP-01 HISTORIAN

Status: ISSUES_FOUND

Spec grounding:
- HL7 FHIRPath N1 §4.1 enumerates Boolean, String, Integer, Decimal, Date, Time, DateTime, and Quantity literals.
- §4.1.2 says string escapes are limited and unknown backslash escapes drop the backslash.
- §4.1.3 defines Integer range as -2^31 through 2^31-1, with unary minus outside the literal.
- §4.1.5 Date has no timezone suffix; §4.1.7 DateTime permits timezone only after a time component; the formal grammar uses `quantity : NUMBER unit?`.

Probes run:
- `.temp/qa/fp01_historian_literal_probe.py` compared native C++ and forced Python fallback on all literal classes listed in `config.notes`.
- Existing focused guard: `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py::test_no_whitespace_quoted_quantity_literals_match_spec_and_backends -q` passed.
- Manual SQL probes compared `fhirpath`, scalar wrappers, and `fhirpath_is_valid` across native and forced fallback.

Issues opened:
- QA-001: `fhirpath_timestamp` and `fhirpath_quantity` return scalar text for non-DateTime/non-Quantity literals in both backends; surrogate-pair strings can crash through those wrongly typed wrappers.
- QA-002: forced Python fallback accepts invalid timezone-suffixed Date/partial-DateTime literals such as `@2014Z` and `@2014TZ` as valid.
- QA-003: native and fallback accept out-of-range Integer literals such as `2147483648` and `(-2147483649)`; fallback also accepts above-int64 values that native rejects.

Suggested remediation:
- Add shared literal precheck helpers for invalid timezone suffixes and Integer range, then use them from both fallback validation and evaluator compilation.
- Add type guards for public timestamp/quantity wrappers in Python fallback and native C++; return SQL NULL unless the first result is the expected FHIRPath literal type.
- Add parity tests covering native/fallback behavior for the three issue clusters.

Post-fix verification:
- `.temp/qa/fp01_historian_literal_probe.py` was rerun after remediation with local workspace imports and backend-isolated subprocesses. Native and forced Python fallback now agree for Boolean, String, Integer, Decimal, Date, Time, DateTime, and Quantity literals; invalid timezone and out-of-range Integer boundaries report `fhirpath_is_valid=false`.
- Focused parity tests pass: `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py -q`.
- Full conformance remains 100.0%: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
