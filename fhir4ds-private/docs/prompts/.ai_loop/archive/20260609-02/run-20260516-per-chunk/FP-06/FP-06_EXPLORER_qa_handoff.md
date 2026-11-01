# QA Handoff - FP-06 EXPLORER

Scope: FHIRPath 5.5.1 iif, 5.5.2 Boolean conversion, and 5.5.3 Integer conversion.

Spec anchor: The normative FHIRPath conversion rules require singleton input for these conversion functions. Boolean conversion accepts only the documented Boolean, Integer/Decimal 0/1, and string representations. Integer conversion accepts Integer, Boolean, and strings matching `(+|-)?\d+`; Decimal inputs such as `1.0` are not convertible to Integer. `iif` evaluates the criterion as Boolean and must only evaluate the selected result branch.

Exploration performed:
- Compared public native DuckDB UDFs and forced Python fallback UDFs for multi-item `toBoolean()`, `toInteger()`, `convertsToBoolean()`, `convertsToInteger()`, lazy `iif` branches, empty `iif` criteria, non-Boolean `iif` criteria, signed/overflow integer strings, whitespace-padded strings, and resource-backed numeric fields.
- Checked direct Python core behavior for decimal-to-integer rejection and strict/non-strict `iif` criterion handling.
- Re-ran isolated native and fallback probes after a transient exploratory mismatch; the mismatch did not reproduce in isolated runs.

Findings: No new reproducible FP-06 bug found. Existing current-source behavior matches the focused FP-06 invariants previously fixed by SKEPTIC/HISTORIAN: native and Python fallback agree for public DuckDB surfaces, multi-item conversion errors become empty/NULL in public UDFs, and core strict evaluation still raises where strict semantic errors are required.

Validation:
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py -q` -> 8 passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/unit/test_conversion.py -q` -> 112 passed.
- `python3 -m pytest fhir4ds/fhirpath/tests/unit fhir4ds/fhirpath/tests/compliance -q -k 'iif or toBoolean or convertsToBoolean or toInteger or convertsToInteger or Conversion'` -> 0 selected; not useful for this suite layout.
- `python3 conformance/scripts/run_fhirpath_r4.py` plus report summary -> 935/935 passed, 0 failed.
