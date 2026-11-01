# Engineer Handoff — FP-18 EXPLORER launch 3 (iteration 1)

## Triage
| ID | Sev | Category | Verdict |
|---|---|---|---|
| QA-001 | MEDIUM | PARITY_SPEC_VIOLATION | CONFIRMED → RESOLVED |
| QA-002 | MEDIUM | PARITY_SPEC_VIOLATION | CONFIRMED → RESOLVED |
| QA-003 | LOW | OBSERVATION | INTENDED (cross-engine-consistent, unpinned) |

## Fixes

### QA-001 — unary-minus Long overflow (§6.6 overflow doctrine)
- Root cause: core `polarity_expression`
  (fhir4ds/fhirpath/engine/evaluators/__init__.py) applied bare Python
  `-unwrapped` with no int64 guard; native `evalUnaryOp` returned `{}` at
  LLONG_MIN instead of degrading to Decimal like the binary `+`/`-`/`*` paths
  (doctrine: `9223372036854775807L + 1L` → `9223372036854775808.0` on both
  engines).
- Fix: core degrades int-negation results outside int64 to
  `Decimal(result)`; native LLONG_MIN branch returns Decimal
  `9223372036854775808.0` (source_text-pinned; 2^63 exact in binary64).
- Extension rebuilt (`make fhirpath_loadable_extension` in
  extensions/fhirpath/build/release) and redeployed md5
  `e58683dfe09cf352dfcde8bf762989ea` to: repository/v1.5.2 test path, repo
  bundle `fhir4ds/fhirpath/duckdb/extensions/`, and user site-packages.
- Verified: `- -9223372036854775808L` → `9223372036854775808.0` on BOTH
  engines; nested `-(- -…L)` → `-9223372036854775808.0`.

### QA-002 — `&` implicit conversion of complex JSON values (§6.6.7)
- Root cause: `math.amp._string_value`
  (fhir4ds/fhirpath/engine/invocations/math.py) used `str(value)` on
  dict/list subtrees → Python repr (`{'value': 3, …}`); native serializes
  compact JSON.
- Fix: dict/list values serialize via `json.dumps(..., separators=(",", ":"),
  ensure_ascii=False)`. Python-only; no rebuild.
- Verified: `qs & ''` → `{"value":3,"unit":"cm","code":"cm"}` identical on
  both engines; nested structures verified; primitive conversions unchanged.

## Regression tests
`fhir4ds/fhirpath/tests/unit/test_fp18_math_operators.py`: new classes
`TestFP18Explorer2026_08_18` (5 core tests) and
`TestDualEngineParityExplorerFP18` (2 dual-engine parity tests) — file now
73/73 passed.

## Recovery Gate
- test_fp18_math_operators.py: 73/73.
- Probe rerun: 0 parity diffs (remaining G-case "failures" are probe-harness
  first-item text reads; verified identical via fhirpath() JSON lists).
- Full conformance + fhirpath pytest tree: run post-handoff (see architect
  handoff for final counts).
