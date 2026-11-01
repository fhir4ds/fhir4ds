# Code Review Findings - review-10

## Scope Reviewed

Milestone review after 10 completed FP spec chunks, focused on FP-06 through FP-10 risk areas:

- Native C++ DuckDB extension parity in `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- Python fallback/wrapper behavior in `fhir4ds/fhirpath/duckdb/udf.py`
- Direct helper APIs in `fhir4ds/fhirpath/duckdb/functions/`
- Core Python conversion/string invocation paths in `fhir4ds/fhirpath/engine/invocations/`
- Regression tests under `fhir4ds/fhirpath/duckdb/tests/`

## Findings

### REV-001 - HIGH - Regex DoS hardening is incomplete in native and direct-helper paths

Evidence:

- `extensions/fhirpath/src/fhirpath/evaluator.cpp:84-103` only limits pattern length before compiling `std::regex`.
- `extensions/fhirpath/src/fhirpath/evaluator.cpp:2417-2422` evaluates user-controlled `matches()` patterns through `std::regex_match`.
- `extensions/fhirpath/src/fhirpath/evaluator.cpp:1995-1998` evaluates user-controlled `replaceMatches()` patterns through `std::regex_replace`.
- `fhir4ds/fhirpath/duckdb/functions/string.py:354-355` and `:388-389` call Python `re.fullmatch` / `re.sub` directly, without the core engine's `_validate_regex()` nested-quantifier guard.

Risk:

Patterns such as nested quantifiers remain able to consume unbounded CPU in native C++ and direct helper APIs. The core Python string invocation path has ReDoS detection, so this is both a security gap and an implementation drift risk.

Recommended remediation:

Move native regex evaluation to a non-backtracking engine such as RE2, or add an equivalent safe-regex validator before `std::regex` compilation. Reuse the same guard policy in `fhir4ds/fhirpath/duckdb/functions/string.py` instead of calling `re` directly.

### REV-002 - MEDIUM - Direct conversion helpers still diverge from FP-06 through FP-08 conversion semantics

Evidence:

- `fhir4ds/fhirpath/duckdb/functions/conversion.py:487-548` lets `to_date("2015-02-04T99")` return `2015-02-04` by truncating the date portion before fully validating the malformed DateTime string.
- `fhir4ds/fhirpath/duckdb/functions/conversion.py:553-613` strips `Z` / offset suffixes in `to_time()`, so `to_time("10:30:45Z")` returns `10:30:45` while the public parity path rejects timezone-bearing Time strings.
- `fhir4ds/fhirpath/duckdb/functions/conversion.py:732-764` strips leading whitespace and accepts quantity strings that the public FHIRPath path rejects, including `" 1"`, `"1 wk"`, and `"1 ''"`.
- `fhir4ds/fhirpath/duckdb/functions/conversion.py:691-712` ignores the optional target unit for Quantity-like dicts.

Probe run:

```text
to_quantity leading {'value': 1.0, 'unit': ''}
to_quantity bare wk {'value': 1.0, 'unit': 'wk'}
to_quantity empty unit {'value': 1.0, 'unit': "''"}
to_quantity unit mismatch {'value': 1, 'unit': 'kg'}
to_date malformed dt 2015-02-04
to_time tz 10:30:45
```

Recommended remediation:

Bring `functions/conversion.py` direct helpers onto the same strict conversion table used by the core engine and public DuckDB UDFs. Add direct-helper regressions for the FP-07/FP-08 cases already covered in public parity tests.

### REV-003 - MEDIUM - Native type reflection embeds model knowledge in generic runtime code

Evidence:

- `extensions/fhirpath/src/fhirpath/evaluator.cpp:201-263` embeds a hand-maintained FHIR type hierarchy.
- `extensions/fhirpath/src/fhirpath/evaluator.cpp:4890-4897` embeds field-name heuristics for `HumanName`, `Address`, `Identifier`, `ContactPoint`, `Coding`, and `CodeableConcept`.

Risk:

The generic native runtime can drift from generated schema/model metadata and will miss resource/profile/type changes unless the static map is manually maintained. This violates the loop invariant that model knowledge should be data-driven.

Recommended remediation:

Load subtype and complex-type metadata from generated FHIR model artifacts or a compact generated registry consumed by the C++ extension. Keep any fallback table generated, versioned, and parity-tested against the Python model metadata.

## Validation Performed

- `pytest -q fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py` - 14 passed.
- `pytest -q fhir4ds/fhirpath/duckdb/tests/unit/test_conversion.py fhir4ds/fhirpath/duckdb/tests/unit/test_string.py` - 215 passed.
- `pytest -q fhir4ds/fhirpath/duckdb/tests/unit/test_filter.py fhir4ds/fhirpath/duckdb/tests/unit/test_convenience_udfs.py` - 158 passed.
- Static searches with `rg` over C++ evaluator, DuckDB UDFs, core invocation modules, and helper functions.

## Residual Risks

Native SQL assertion suites and full conformance were not rerun during this review. The bundled extension binary was present in the diff and the Python parity slices exercised the installed public UDF surface, but this review did not rebuild the native extension.
