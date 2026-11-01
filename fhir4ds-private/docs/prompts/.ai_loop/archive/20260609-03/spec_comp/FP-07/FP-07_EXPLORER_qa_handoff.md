# QA Handoff: FP-07 EXPLORER

Scope: FHIRPath Normative Release §5.5.4 Date Conversion, §5.5.5 DateTime
Conversion, and §5.5.6 Decimal Conversion. Personality: EXPLORER.

Spec grounding: https://hl7.org/fhirpath/N1/ defines conversion functions as
singleton-only. `toDate()` and `convertsToDate()` accept Date, DateTime, and
String inputs convertible to Date; `toDateTime()` and `convertsToDateTime()`
accept DateTime, Date, and String inputs convertible to DateTime; `toDecimal()`
and `convertsToDecimal()` accept Integer, Decimal, Boolean, and String inputs
matching `(\+|-)?\d+(\.\d+)?`. Empty input returns empty, and multi-item input
signals an error to the calling environment.

Fresh probe: `.temp/qa/fp07_explorer_rerun_probe.py`

EXPLORER hypotheses tested:
- Invalid date/time ranges and timezone shapes could pass native parsing.
- Partial precision Date/DateTime values could lose precision in conversion
  chains.
- Decimal grammar edges such as signs, whitespace, exponent notation, and
  punctuation could drift between native C++ and forced Python fallback.
- Runtime singleton errors inside lazy `iif()` or projection chains could be
  evaluated eagerly or misclassified.
- Conversion predicates nested inside filters/projections could diverge between
  backends.

Results:
- Probe: 46 cases, native extension loaded, forced Python fallback active,
  `mismatch_count=0`, `expectation_failure_count=0`.
- Focused pytest: `test_conversion_parity.py` passed, 16 tests.
- Native extension test: `402 assertions in 2 test cases`.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

No FP-07 issues were logged. Two adjacent observations were not logged as FP-07
bugs: data-dependent resource-backed multi-item conversion errors can leave
`fhirpath_is_valid()` true while result UDFs return empty/NULL, and Decimal
string spelling after `toDecimal().toString()` may use more than one
spec-valid representation.

Recommendation: no remediation required.
