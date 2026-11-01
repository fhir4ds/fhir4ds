# Engineer Handoff — CQL-03 Spec Compliance, iter 1 (Remediation) — 2026-08-20

## QA-001 RESOLVED — same-code quantity comparison used table/pint validity, not UCUM grammar (HIGH)
- Root cause: native `same_code_unit_valid_for_compare()` only accepted units
  present in the 85-entry conversion table; the Python mirror deferred to
  pint, which is case-insensitive and accepts invalid bare prefixes. Both
  engines also treated `*` as a compound separator, so UCUM power prefixes
  (`10*3/uL`) could never validate.
- Fix (lockstep, both engines):
  - `extensions/cql/src/cql/quantity.cpp`: new `is_ucum_metric_prefix()`,
    `is_known_ucum_symbol()` (table ∪ {'l','G'}), `is_valid_ucum_atom()`
    (power-of-ten terms `10*n`/`10^n`, metric-prefix + symbol incl. two-char
    `da`, single-digit exponent suffixes `cm3`/`m3`); compound separator set
    `"/."` (no `*`).
  - `fhir4ds/cql/duckdb/udf/quantity.py`: mirrored
    `_UCUM_VALIDITY_SYMBOLS` (generated from the native table keys),
    `_is_valid_ucum_atom()`, structural compound walk; same-code INVALID
    units now return None instead of falling through to pint (which wrongly
    rescued `5 'M' = 5 'M'` to True).
- Spec grounding: CQL 1.5 §Equal (Quantity) — invalid (non-UCUM) units →
  null; UCUM case-sensitive grammar (G gauss, Mg megagram, MG megagauss,
  ML megaliter, ml milliliter, 10*3/uL valid; bare 'M' invalid).
- Extension rebuilt (`make cql_loadable_extension`), md5
  `3da236e1fb13c991704fc89acce5a65d`, deployed to repo bundle AND
  site-packages, verified through reloaded connections.
- Residual filed as QA-004 LOW DEFERRED: cross-code conversions between
  metric-prefixed units (5 'ML' < 5 'ml', 5 'kg' = 1000 'dag') still null on
  native — needs prefix-aware conversion algebra (FP-18 deferred family).

## QA-002 RESOLVED — Ratio tuple-selector equality broken (HIGH)
- Root cause: `_translate_instance_expression` emitted
  `Ratio { numerator: X, denominator: Y }` via the generic json_object path
  with raw scalar / double-encoded-string components; `_parse_valid_ratio`
  rejected the shape, so `=` → null and `~` → false even for identical
  Ratios.
- Fix: new `_fold_ratio_instance()` in `_lists.py` emits canonical FHIR
  Ratio JSON with quantity-object components
  (`json_object('numerator', CAST(parse_quantity(...) AS JSON), ...)`);
  Integer/Decimal components implicitly convert to unit-'1' quantities;
  null components and `Ratio { }` preserved (null propagation per §Equal).
  Accessors (`.numerator`, `.numerator.value`) and `ToString` verified
  unchanged on both backends.
- Spec grounding: CQL 1.5 §Types Ratio — constructor takes Quantity
  components; equality is component-wise Quantity equality.

## QA-003 RESOLVED — MinValue/MaxValue untranslated passthrough (MEDIUM)
- Root cause: `MinValue(Date)` etc. fell through `_translate_function_ref`
  to literal SQL (`minvalue` — no such DuckDB function → Catalog Error).
- Fix: `_translate_min_max_value()` constant fold in `_functions.py` for
  Integer, Long, Decimal, Date, DateTime, Time per CQL 1.5 Appendix B-A;
  unsupported types (e.g. String) raise typed TranslationError (no silent
  fallback).

## Files changed
- `extensions/cql/src/cql/quantity.cpp` (+ atom validity, separator fix)
- `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension` (rebuilt bundle)
- `fhir4ds/cql/duckdb/udf/quantity.py` (mirror + no-pint-rescue)
- `fhir4ds/cql/translator/expressions/_lists.py` (Ratio fold)
- `fhir4ds/cql/translator/expressions/_functions.py` (Min/MaxValue fold)
- `fhir4ds/cql/duckdb/tests/integration/test_temporal_complex_parity.py`
  (+3 tests, file now 20 passing)

## Validation (Recovery Gate)
- Chunk parity file: 20/20 pass (was 17 + 3 new).
- CQL duckdb suite: 780 passed, 5 skipped (0 failures).
- Full conformance: ViewDefinition 144/144, FHIRPath 935/935, CQL
  1706/1706, DQM 47/47, OVERALL 2832/2832 — baseline held
  (`.temp/qa/cql03_historian2_2026_08_20/validation.log`).

All issues terminal: QA-001/002/003 RESOLVED, QA-004 DEFERRED (LOW,
documented family). No NEEDS_CONTEXT.
