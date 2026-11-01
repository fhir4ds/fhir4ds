# QA Handoff: FP-07 HISTORIAN

## Scope

- Chunk: FP-07
- Personality: HISTORIAN
- Spec focus: FHIRPath Normative Release §5.5.4 Date Conversion, §5.5.5
  DateTime Conversion, and §5.5.6 Decimal Conversion.
- Functions tested: `toDate()`, `convertsToDate()`, `toDateTime()`,
  `convertsToDateTime()`, `toDecimal()`, and `convertsToDecimal()`.

## Spec Grounding

- Function signatures are zero-argument invocation functions; optional
  parameters are explicitly marked in signatures, and these conversion
  signatures have none.
- Empty input returns empty. Multi-item input is a singleton-evaluation error;
  the public DuckDB wrappers convert those row-level errors to empty/NULL and
  `fhirpath_is_valid=false` for constant invalid expressions.
- Date conversion accepts Date, DateTime, and strings convertible to Date.
  Date values use year, year-month, or full-date precision in the valid
  calendar range.
- DateTime conversion accepts Date, DateTime, and strings convertible to
  DateTime. Partial DateTime precision and `T` suffixes are preserved; timezone
  offsets require full `+/-hh:mm` shape and valid time fields.
- Decimal conversion accepts Integer, Decimal, Boolean, and strings matching
  the strict decimal grammar `(+|-)?\d+(\.\d+)?`; exponent notation, leading
  dot, trailing dot, and whitespace-padded forms are not decimal strings.

## Probe Summary

- Created `.temp/qa/fp07_historian_probe.py`.
- Inserted the workspace root into `sys.path` to avoid installed-wheel drift.
- Opened separate native C++ and forced Python fallback DuckDB connections and
  asserted the native connection actually loaded the bundled extension while
  the forced fallback did not.
- Ran 56 cases covering valid/invalid lexical forms, calendar ranges,
  timezone range/shape checks, partial DateTime precision, decimal grammar,
  empty input, multi-item input, invalid arity, and resource-backed strings.
- Compared `fhirpath`, `fhirpath_text`, `fhirpath_json`, `fhirpath_number`,
  `fhirpath_date`, `fhirpath_timestamp`, `fhirpath_bool`, and
  `fhirpath_is_valid`.

## Results

- Fresh probe: 56 cases, 0 native/fallback mismatches, 0 expectation failures.
- Focused pytest: `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`
  passed, 16 tests.
- Issues logged: none.

## Handoff

No remediation is required for FP-07 HISTORIAN. The public DuckDB native and
forced fallback behavior matched the spec-grounded expectations for this
section.
