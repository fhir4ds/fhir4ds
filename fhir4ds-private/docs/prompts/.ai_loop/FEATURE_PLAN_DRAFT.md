# FEATURE PLAN DRAFT — WASM function-surface parity (v1)

## Objective

Close the remaining desktop ↔ DuckDB-WASM function-surface gaps for everything
the CQL translator can emit, with behavioral parity, and make the gap class
visible to CI (behavior contract, not name contract).

S32 already fixed `ToDate` (C++ scalar, TS macro removed). This plan covers the
rest of the conversion surface and the contract upgrade.

## Evidence (three-connection audit, 2026-10-24)

Connections compared:

1. **wasm-equivalent**: C++ extensions only (`fhirpath` + `cql`), no Python UDFs.
2. **desktop**: `fhir4ds.cql.duckdb.register()` (C++ + Python supplements/shadows
   + Python SQL macros).
3. **browser macros**: names extracted from `web/cql-cleanroom/src/lib/cql-macros.ts`.

Results:

- 48 public desktop-only names absent from the browser (list-equality macros
  already allowlisted; the rest are conversion functions).
- 76 names present on both sides with different implementations (name parity
  only).
- `fhir4ds/operations/tests/test_macro_sync.py` enforces macro **names** and
  carries a 22-entry `BROWSER_MACRO_GAP_ALLOWLIST`.

## Surface classification

### Class A — desktop implementations are pure SQL macros (browser can/should
use the same SQL)

`ToString`, `ConvertsToString`, `ToInteger`, `ToDecimal`, `ToBoolean`,
`ConvertsToInteger`, `QuantityToString`, and the other pure-SQL macros in
`fhir4ds/cql/duckdb/macros/*.py`.

Browser status: `ToString`/`ToInteger`/`ToDecimal`/`ToBoolean` are naive
`CAST(...)` macros; `ConvertsToInteger`/`ConvertsToString` exist with partial
semantics. These diverge from Appendix B (e.g. `ToInteger('1.0')` must be NULL,
`ToDecimal('1e2')` must be NULL, `ToBoolean('yes')` must be true,
`ToString(DECIMAL)` must trim trailing zeros).

Plan: replace the TS bodies with the desktop macro bodies verbatim (formatted
final SQL), so both surfaces run the same SQL. No C++ needed.

### Class B — desktop implementations are Python UDFs (need native C++)

| Function | Desktop source | Notes |
|---|---|---|
| `ToDateTime` | `udf/conversion.py::ToDateTime` via `__cql_to_datetime` | calendar/time/tz validation, partial precision, Z→+00:00 |
| `ToTime` | `udf/conversion.py::ToTime` | T-prefix output, tz normalization |
| `ToLong` | `udf/conversion.py::ToLong` | int64 range, boolean overload |
| `ToRatio` | `udf/conversion.py::ToRatio` | `q:q` text, JSON Ratio identity |
| `ConvertsToBoolean/Date/DateTime/Decimal/Integer/Long/Quantity/Ratio/String/Time` | `udf/conversion.py` | conversion checks; null → NULL |
| `CanConvertQuantity` | `udf/quantity.py` | target-unit conversion check |

C++ implements these as `RegisterSpecialScalar` VARCHAR→VARCHAR/BOOLEAN
functions in `extensions/cql/src/cql_extension.cpp`, mirroring the Python
authority. Desktop keeps the Python shadow (conformance authority); wasm uses
C++.

### Class C — intentional browser gaps (keep allowlisted)

- List-equality / deep-comparator family (`CQLListEqualEq`, `CQLListIntersectEq`,
  `CQLTupleValueEqual`, nested JSON equality, …): the cleanroom evaluates
  population measures that do not emit them; porting the macros requires the
  JSON-normalization helpers.
- `ExpandValueSet`: requires the terminology `valuesets` table (no browser data
  tier).
- `CQLListMode`: dynamically composed.
- `ToDate` (now native-provided; allowlist entry documents why the TS macro was
  removed).

## Architecture

- **Single implementation per function on each transport**: pure-SQL macros are
  byte-identical across desktop/browser; Python-UDF-backed functions get a C++
  mirror for the no-Python path.
- **Harness**: a Python test-only module
  `fhir4ds/operations/tests/wasm_surface_harness.py` that:
  1. opens a native connection, loads both `.duckdb_extension` files;
  2. extracts every `CREATE ... MACRO ...` string from `cql-macros.ts` and
     executes it (same regex as `test_macro_sync.py`);
  3. exposes `browser_query(sql)`.
  Desktop reference uses `register()`.
- **Corpus**: Appendix B examples + edge cases per function (invalid dates,
  leap years, offsets, partial precision, `1.0`/`1e2`/`yes`, Quantity/Ratio
  shapes, nulls, multi-row).
- **Contract test**: `test_macro_sync.py` grows a behavior check for
  non-allowlisted duplicates (same value + DuckDB type) and a "native-provided"
  section for removed TS macros.

## Implementation plan

1. Harness + corpus (test-only; no production change).
2. C++ ports, in this order (shared helpers first):
   `ToDateTime`/`ToTime` (date/time parsers already added for `ToDate`),
   `ToLong`, `ToRatio`, `ConvertsTo*`, `CanConvertQuantity`.
3. `cql-macros.ts`: copy Class A bodies; remove macros now served natively
   (`ToDateTime`, `ToTime`; keep `ToString`/`ToInteger`/`ToDecimal`/`ToBoolean`
   as aligned macros unless a native body is required by type constraints).
4. `test_macro_sync.py`: behavior contract + allowlist prune.
5. Rebuild native + WASM extensions; md5-verify deployment; rebuild the wheel;
   deploy the Cleanroom targets; rerun all gates.

## Test strategy

- Dual-engine harness parity per function (`browser` vs `desktop`).
- `no_python_connection` tests for every ported function (no Python UDFs).
- Standalone e2e: cms125 cells + console/views; assert no Catalog/Binder errors.
- Master conformance 2832/2832; full pytest trees; vitest; clean-venv smoke.

## Risks

- C++ date/time validation must match Python exactly (offset bounds, partial
  precision, `T` marker, leap years); reuse the S32 `ToDate` parsers.
- Quantity/Ratio JSON shape rules are subtle (value required, finite Decimal).
- `ConvertsTo*` null semantics: input NULL → NULL (not false).
- Elapsed effort: 8–10 functions + harness; keep the port order so each function
  ships green independently.
