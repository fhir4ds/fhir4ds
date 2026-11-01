# QA Handoff - FP-14 HISTORIAN

Spec chunk: FHIRPath 6.2 Comparison.
Personality: HISTORIAN.

Spec source consulted: official HL7 FHIRPath continuous-build source,
`input/pages/index.md`, especially the 6.2 Comparison rules for singleton
operands, empty propagation, supported ordered types, Quantity conversion, and
Date/DateTime/Time ordering.

Fresh probe created:
- `.temp/qa/fp14_historian_fresh_probe.py`

Coverage:
- Native DuckDB/C++ registration and forced Python fallback registration.
- Public `fhirpath`, `fhirpath_json`, `fhirpath_bool`, `fhirpath_text`,
  `fhirpath_number`, and `fhirpath_is_valid` outputs.
- Numeric Integer/Long/Decimal ordering, including large exact values around
  binary64 precision boundaries.
- Quantity literal and resource-backed comparisons, including same-unit exact
  ordering, UCUM-convertible units, incompatible dimensions, and calendar-vs-
  UCUM duration indeterminacy.
- Date, DateTime, Time, string, empty, multi-item, and non-comparable operand
  behavior.
- Review-10 findings were checked for intersection; none directly affect this
  comparison chunk except the general requirement to keep validity and public
  wrappers aligned.

Issues found:
- `QA-001` MEDIUM `SPEC_VIOLATION`: forced Python fallback orders
  resource-backed DateTime paths with timezone offsets by local string/time
  components rather than normalized instants. Reproducer:
  `effectiveDateTime > issued` over `2015-02-04T10:00:00+01:00` and
  `2015-02-04T09:30:00Z` returns native false but fallback true. Correct result
  is false because the left instant is 09:00Z and the right instant is 09:30Z.

Validation performed during QA:
- `python3 .temp/qa/fp14_historian_fresh_probe.py` failed on `QA-001`.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py::test_large_exact_numeric_and_quantity_comparisons_match_python_fallback -q` passed, confirming the prior large-number/native precision fix is present in the current extension.

Next phase:
- Remediation should fix fallback DateTime comparison for resource-backed
  values carrying timezone offsets, then add focused native/fallback parity
  coverage to `test_comparison_parity.py`.
