# IMPLEMENTATION HANDOFF — WASM function-surface parity

## Done

**Class A (no C++; browser macros now carry desktop SQL verbatim)**
`ToString`, `ToInteger`, `ToDecimal`, `ToBoolean`, `ConvertsToString`.
Extracted from `duckdb_functions().macro_definition`; `cql-macros.ts` updated.

**Class B (C++ mirrors for the no-Python runtime)**
`ToDateTime`, `ToTime`, `ToLong`, `ToRatio`,
`ConvertsToBoolean/Date/DateTime/Decimal/Integer/Long/Quantity/Ratio/String/Time`,
`CanConvertQuantity` — `RegisterSpecialScalar` functions in
`extensions/cql/src/cql_extension.cpp`; VARCHAR transport; null-resilient.

**Grammar/guards**
- `cql::to_quantity` accepts bare calendar duration keywords (`5 years`) per
  CQL-06; bare UCUM still rejected.
- JSON Quantity decimal-extent guard (30 integer digits) applied at the
  conversion checks only; `parse_quantity_json`/`quantityConvert` unchanged.

**Architecture**
- Desktop authority preserved: new UDF names added to
  `_PYTHON_PREFERRED_CPP_CONFLICTS` (`fhir4ds/cql/duckdb/extension.py`), so
  `register()` shadows C++ with Python; C++ serves WASM.
- `ToDateTime`/`ToTime`/`ConvertsToInteger` TS macros removed (native wins);
  `ToDate`/`ToDateTime`/`ToTime` allowlisted in `test_macro_sync.py` as
  native-provided.

**Correctness harness**
`fhir4ds/operations/tests/wasm_surface_harness.py` + `test_wasm_surface_parity.py`:
browser-equivalent surface (C++ extensions + TS macros verbatim) vs desktop vs
SPEC-EXPECTED `(value, typeof)`. 59 Class A/B cases.

## Where (artifacts)

- Native cql ext md5 `bd8ec2890912b623faff4c24d8ceb4b7` — build == repo bundle ==
  site-packages.
- WASM cql ext md5 `5bc222aa060a68495d44ac89c0dd4672` — build == both public
  extension dirs.
- Wheel `fhir4ds_v2-0.0.18-py3-none-any.whl` md5 `0f4760eec67bb4622b52ca533d509000`
  (contains `bd8ec289…`), deployed to all Cleanroom static targets + wasm-demo
  + website snapshots.
- Standalone: cms125 cells run clean (17 cells, no Catalog/Binder errors).

## Gates

- Conformance **2832/2832** (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).
- Targeted conversion/parity suites: 83 passed.
- fhirpath+viewdef+dqm+devserver+operations+tests: **4046 passed**, 2 failures
  are the documented pre-existing FHIRPath parity gaps (FP-14 temporal-string
  ordering, FP-10 matches-flag); fhirpath binary untouched by this campaign.
- Vitest 197 passed.
- Full `fhir4ds/cql` tree: running in PTY (result to be appended).

## Deviations / open

- `GAP-001` (MEDIUM): native `ToQuantity` renders integer-authored values as
  `"value":10.0` vs desktop `"value":10` (JSON spelling; semantic value equal).
  Not in this campaign's Class A/B scope; candidate fix = integer-authorship
  flag in `ParsedQuantity` + quantity-arithmetic regression sweep.
- `GAP-002` (LOW): Class C allowlist unchanged (list-equality family,
  `ExpandValueSet`, `CQLListMode`).
- The TS `ToDate` macro removal is recorded in the allowlist with a
  native-provided justification.
