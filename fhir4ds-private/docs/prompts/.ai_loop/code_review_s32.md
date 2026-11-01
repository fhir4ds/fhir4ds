# CODE REVIEW — WASM function-surface parity (S32)

Scope: the campaign delta — `extensions/cql/src/cql_extension.cpp` (+983),
`extensions/cql/src/cql/quantity.cpp` (+23), `fhir4ds/cql/duckdb/extension.py`
(+15), `web/cql-cleanroom/src/lib/cql-macros.ts` (5 bodies aligned, 3 macros
removed), the new three-way harness + tests, and the docs
(AGENTS.md / releases.md / plan).

## Verification performed

- **Security:** no new dynamic SQL built from user values (all conversion
  functions parse strings; no interpolation into SQL); yyjson documents and
  writers are freed on every path in `ConvertsRatioJson`; no secrets/logging.
- **Error integrity:** conversion functions are null-resilient at the SQL
  boundary (invalid → NULL/false, never raise); the decimal-extent guard is
  scoped to conversion checks and does **not** alter
  `parse_quantity_json`/`quantityConvert` (verified by the boundary suite).
- **Architecture:** desktop keeps the Python conformance authority via
  `_PYTHON_PREFERRED_CPP_CONFLICTS` (verified: `register()` uses the Python
  UDFs; native-only uses the C++ mirrors); Class A macros are byte-identical
  to the desktop bodies; allowlist entries are justified and pruned by the
  existing contract test.
- **Correctness:** 69 three-way harness cases (expected vs desktop vs browser,
  value + `typeof`), targeted conversion suites 83, conformance 2832/2832,
  vitest 197; standalone cms125 cells clean; artifact md5 parity
  (native `bd8ec289…`, wasm `5bc222aa…`, wheel `0f4760ee…`).

## Findings

- **CR-001 (LOW, note):** `ConvertsToFunc` uses `Value::GetValue` per row for
  non-VARCHAR inputs (slow path). VARCHAR — the translator's transport — takes
  the fast UnifiedVectorFormat path. Acceptable.
- **CR-002 (LOW, note):** `CompactIntegralQuantityValue` rewrites
  `"value":N.0` → `"value":N` textually to match desktop Ratio serialization;
  covered by the `ToRatio('5 years:2 days')` corpus case.
- **CR-003 (LOW, note):** the harness loads the build-tree extension; release
  gates already md5-verify build == bundle == site-packages == wasm public.
- **CR-004 (MEDIUM, inherited):** `ToQuantity` still emits `10.0` natively vs
  `10` on desktop for integer-authored values (GAP-001). Semantically equal
  JSON numbers; candidate follow-up needs a `ParsedQuantity` integer-authorship
  flag plus a quantity-arithmetic sweep (arithmetic intentionally renders
  reals).
- **CR-005 (LOW, inherent):** Class B now has dual implementations (Python
  authority + C++ mirror); the three-way harness is the drift guard. Do not
  add a new mirrored function without a harness case.

## Verdict

**CLEAN_WITH_NOTES** — no CRITICAL/HIGH findings; the MEDIUM is a documented
pre-existing representational gap outside the Class A/B scope.
