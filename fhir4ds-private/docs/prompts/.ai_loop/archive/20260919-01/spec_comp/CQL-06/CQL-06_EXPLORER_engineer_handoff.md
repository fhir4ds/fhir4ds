# Engineer Handoff — CQL-06 FIX (iteration 1, resumed launch)

Date: 2026-08-20. Workflow: evolution, phase FIX. All 3 QA issues remediated at root cause.

## Fixes

### QA-001 (HIGH) — FHIR primitive `.value` accessor
- Sites: `fhir4ds/cql/translator/expressions/_property.py`
  - `_strip_primitive_value_segments()` (new helper, data-driven from
    `fhir4ds/fhirpath/models/r4/path2Type.json`): drops a `value` segment
    when the accumulated path prefix resolves to a FHIR primitive type.
    Applied at the two fhirpath chain-merge sites and in
    `_flatten_fhirpath_source()`.
  - Identity mapping for `(X as FHIR.<primitive>).value` at the `as`-unwrap
    site. Resumed-launch fix: the cast target is model-qualified
    (`"FHIR.string"`, a `NamedTypeSpecifier`), so the primitive check now
    compares the bare last path component — this was why
    `(O.value as FHIR.string).value` still returned NULL after the first
    (interrupted) fix attempt.
- Verified: `P.birthDate.value` → `['1980-01-01']`, `P.gender.value` →
  `['male']`, `O.status.value` → `['final','final']`,
  `(O.value as FHIR.string).value` → `['42','high']`,
  `Count/Sum(... where ConvertsToInteger((O.value as FHIR.string).value))`
  → 1 / 42 on BOTH the forced-python and native-extension connections.

### QA-002 (MEDIUM) — ConvertsToDecimal too strict
- `fhir4ds/cql/duckdb/udf/conversion.py`: `_DECIMAL_STRING_RE` accepts any
  fractional digit count (format `(+|-)?#0(.0#)?` per CQL 1.5 App. B);
  representability gate is now `_fits_duckdb_decimal_rounded()` — only the
  integer-digit extent (30 digits for DECIMAL(38,8)) is a hard limit;
  excess fractional scale rounds exactly like ToDecimal (CQL-01 doctrine).

### QA-003 (MEDIUM) — ConvertsToTime/ToTime admitted timezone offsets
- `udf/conversion.py`: `_TIME_RE` timezone group removed; `_is_valid_cql_time`
  no longer validates tz; `ToTime` no longer strips offsets (invalid input →
  null per spec: CQL Time carries no timezone; only DateTime may offset).
  ToTime now returns the T-prefixed transport form consistently.

## Terminal states
- QA-001 RESOLVED, QA-002 RESOLVED, QA-003 RESOLVED (regression tests below).

## Tests
- `fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py`:
  - corrected stale expectation `ConvertsToDecimal('1.123456789')` False→True
    (it enshrined the bug QA-002 filed) and added `'0.0000000001'`;
  - new `test_cql_converts_to_decimal_and_time_mirror_to_functions_cql06_explorer`
    (QA-002 + QA-003, dual-backend);
  - new `test_cql_fhir_primitive_value_accessor_yields_system_scalar_cql06_explorer`
    (QA-001, translator → population SQL → dual-backend execution).
- File result: 11/11 passed.

## Out-of-chunk observations (NOT filed, per QA precedent)
- `return Tuple { ... }` columns are projected by population SQL as resource
  references (`$.resourceType || '/' || $.id`), yielding NULLs — independent
  of `.value` (reproduced with `Tuple { b: P.birthDate }` and `Tuple { b: 'x' }`).
  Recommend a dedicated QA probe in a structural/tuple chunk.
- ConvertsToQuantity/ToQuantity still hard-reject >8 fractional digits
  (ToQuantity('1.123456789 mg') → null) — same class as QA-002 but QA scoped
  the filing to Decimal; noted for a future pass.

## Validation
- Full conformance suite run per PROC_VALIDATION.md — results recorded in
  architect_handoff.md / GLOBAL_KNOWLEDGE.md (see below).
