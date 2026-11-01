# CQL-07 Iteration 1 — QA Handoff (EXPLORER)

**Chunk**: CQL Type Operators - Conversions
**Spec**: HL7 CQL Reference v1.5.3 Appendix B (Type Operators - Conversions)
**Personality**: EXPLORER (Fuzzer / Pathological Inputs)
**Date**: 2026-07-01

## Methodology

1. Read source code:
   - `fhir4ds/cql/duckdb/macros/conversion.py` — DuckDB SQL macros (ToBoolean, ToInteger, ToDecimal, ToString, ConvertsToString).
   - `fhir4ds/cql/duckdb/udf/conversion.py` — Python UDFs (ConvertsTo*, ToDate, ToDateTime, ToTime, ToLong, ToRatio).
   - `fhir4ds/cql/duckdb/udf/quantity.py` — `toQuantity`, `toConcept`, Ratio parsing helpers.
   - `extensions/fhirpath/src/fhirpath/evaluator.cpp` — Native C++ `fn_toQuantity` and `formatDecimalNumber`.
2. Loaded the HL7 CQL v1.5.3 normative spec for each conversion operator.
3. Fuzzed 300+ pathological inputs across all 11 conversion operators comparing:
   - Native C++ (lowercase `toBoolean`, `toDecimal`, `toQuantity`, etc.)
   - DuckDB SQL macro (CamelCase `ToBoolean`, `ToDecimal`, `ToQuantity`, etc.)
   - Python UDF (`ConvertsTo*` family)
4. Test vectors covered:
   - Extreme precision Decimals (30-digit int, 9-scale fraction).
   - Polymorphic inputs (bool, int, float, decimal, JSON, list).
   - Unicode in strings (Arabic-Indic digits, BOM, Unicode unit `℃`).
   - Boundary conditions (LONG_MAX+1, year 0001/9999/10000, TZ +14:01).
   - Malformed JSON, malformed Quantity/Ratio strings.
   - Deep conversion chains: ToX(ToY(ToZ(...))).

## Parity Result (Native C++ vs Python UDF)

**Zero parity divergences across ~200+ fuzz inputs** for: ToBoolean, ToDecimal,
ToDate, ToDateTime, ToTime, ToQuantity, ConvertQuantity, ConvertsToQuantity.
Native and Python paths agree on all conversions including pathological Unicode
digits, malformed dates, TZ boundaries, integer-overflow Long/Integer strings.

## Spec Violations Found

### FUZZ-007 (MEDIUM — DATA_HANDLING): ToRatio JSON input echoed verbatim

**Spec**: CQL §22.32 ToRatio only defines a String overload
(`<quantity>:<quantity>`). JSON-object Ratio input is a beyond-spec extension
this implementation accepts. The DATA_HANDLING bug is **internal
inconsistency**: text-input is normalized to canonical form (adds `code` /
`system` fields from `unit`), but JSON input is echoed **verbatim**, leaving
the produced Ratio with inconsistent field structure.

**Reproducer**:
```python
from fhir4ds.cql.duckdb.udf.conversion import ToRatio
ToRatio("5 'mg' : 10 'mg'")
# '{"numerator":{"value":5,"unit":"mg","code":"mg","system":"http://unitsofmeasure.org"},
#   "denominator":{"value":10,"unit":"mg","code":"mg","system":"http://unitsofmeasure.org"}}'
ToRatio('{"numerator":{"value":5,"unit":"mg"},"denominator":{"value":10,"unit":"mg"}}')
# '{"numerator":{"value":5,"unit":"mg"},"denominator":{"value":10,"unit":"mg"}}'
#  ^^^ echoed input verbatim — no code/system normalization
```

**Impact**: Downstream consumers comparing Ratio outputs see different field
sets depending on input form. Round-trip invariant (ToString(ToRatio(x)) ==
x form) does not hold for the JSON-input path.

## Not-A-Bug Registry Entries (Investigated, Spec-Compliant)

- **ToInteger(DECIMAL) returns NULL**: Spec §9.5 ToInteger overloads are
  Boolean/String/Long only — Decimal input is correctly rejected.
- **ToDecimal returns DECIMAL(38,8)** rendering (e.g., `1.00000000` for
  `ToDecimal(TRUE)`): per spec, true→1.0 / false→0.0; DECIMAL storage preserves
  8-scale precision. Round-trip invariant holds via ToString trailing-zero trim.
- **ToQuantity(`5 'mg'`) outputs `"value":5`** (not `5.0`): matches the C++
  native path's `q_is_integer` heuristic (FP-18 SKEPTIC, 2026-06-30).
- **ToRatio accepts colon without spaces** (`"5 'mg':10 'mg'"`): spec defines
  `<quantity>:<quantity>` separator without whitespace requirement.
- **ToDate accepts datetime strings and drops time portion**: per spec
  §9.7 ToDate String overload "can take datetime formatted strings and will
  ignore the time portions".
- **ToBoolean rejects whitespace-padded `' true '`**: spec §9.2 Table 9-F
  defines the exact accepted string set, and `' true '` is not in it.
- **ToConcept rejects Quantity-lookalike** `{"value":5,"code":"mg",...}`:
  correctly identified as Quantity, not Code.
- **ToLong(Boolean) → 1/0**: spec §9.4 explicitly defines this overload.

## Issues Logged

- FUZZ-007: MEDIUM, DATA_HANDLING, OPEN. See `evolution.json`.

## Files Touched (QA Phase Only — No Source Edits)

- `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/cql07_explorer/fuzz.py` — initial harness
- `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/cql07_explorer/fuzz2.py` — parity v2
- `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/cql07_explorer/fuzz3.py` — parity v3 (fixed)
- `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/cql07_explorer/fuzz4.py` — ConvertQuantity + spec checks
- `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/cql07_explorer/fuzz5.py` — deep chains + edge cases
