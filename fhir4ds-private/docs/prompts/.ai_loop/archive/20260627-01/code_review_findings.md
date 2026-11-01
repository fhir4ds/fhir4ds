# 0.0.10 Code Review Findings

**Reviewer**: CODE_REVIEWER (per `ROLE_CODE_REVIEWER.md`)
**Campaign scope**: `git diff 7a758a4f..HEAD` — 16 commits, 90 files, +8,169 / −1,653 lines
**Date**: 2026-06-24
**Slices reviewed**: CQL translator · FHIRPath C++ extension · FHIRPath Python engine / DuckDB UDF · Release / Docs / Packaging

## Summary

| Severity | Count | Release-blocking? |
|----------|-------|-------------------|
| CRITICAL | 1     | Yes — public release-notes misrepresent a shipped fix as a known limitation |
| HIGH     | 4     | Yes — spec parity gap, spec-nonexistent API, and silent WASM version drift |
| MEDIUM   | 9     | Track — spec-semantics drift, error swallowing, parity gaps |
| LOW      | 12    | Track — documentation, idiomatic, type-hint debt |

**Overall health**: Code review **passes** for the implementation slices (CQL, C++, Python engine) — no CRITICAL/HIGH findings in source logic, no SQL injection, no new hardcoded model knowledge, no resource leaks, no UB. The release-blocking findings are concentrated in **release-surface coherence** (release notes + WASM wheel drift), which the `pre_release` and `docs_audit` gates downstream in the pipeline are scoped to resolve.

The 0.0.10 campaign's four headline concerns (CQL cross-library define references, FHIRPath `is()` empty-collection parity, choice-type parity, cql-server CLI docs) are **all verified shipped and correct** in source. The CRITICAL finding is purely that the release *notes* still describe one of them as a limitation.

---

## Release-blocking findings (must resolve before scribe)

### REV-REL-001 — `releases.md` 0.0.10 Known Limitations claim `is()` is reverted, but the fix is shipped — CRITICAL
- **File**: `web/website/docs/getting-started/releases.md:48-57`
- **Category**: RELEASE_NOTES_ACCURACY
- **Evidence**: Commit `b8fc8562` added the `is()` limitation paragraph when commit `8f71e9dd` reverted the fix. Commit `e0ee5119` then re-applied the fix to both Python (`fhir4ds/fhirpath/engine/invocations/types.py:55-61`) and C++ (`fn_isType`), but the release notes were never updated. The referenced pytest `TestIsLowercaseTypes::test_empty_collection_returns_empty` now PASSES. Users reading releases.md will believe `is()` is broken when it is not.
- **Fix**: Move the `is()` bullet from Known Limitations to Highlights. Suggested wording:
  > **FHIRPath `is()` Empty-Collection Parity**: `is()` now propagates the empty collection per FHIRPath §5.1 on both the native C++ engine and the Python fallback, resolving the long-standing `TestIsLowercaseTypes::test_empty_collection_returns_empty` case.
- **Likely duplicate**: The cross-library define paragraph at `releases.md:38-46` likely has the same drift (commit `3ad5d79b` re-applied the fix at HEAD). Flag for `docs_audit` gate confirmation.

### REV-REL-002 — 0.0.10 wheel not copied into WASM demo asset directories — HIGH
- **File**: `web/wasm-demo/public/` (consumed by `web/wasm-demo/vite.config.ts:20`)
- **Category**: VERSION_COHERENCE / WASM_DRIFT
- **Evidence**: `./dist/fhir4ds_v2-0.0.10-py3-none-any.whl` exists at repo root, but every WASM asset directory still holds the 0.0.9 wheel:
  ```
  web/wasm-demo/public/fhir4ds_v2-0.0.9-py3-none-any.whl
  web/wasm-demo/dist/fhir4ds_v2-0.0.9-py3-none-any.whl
  web/wasm-demo/dist/assets/fhir4ds_v2-0.0.9-py3-none-any.whl
  web/website/build/wasm-app/fhir4ds_v2-0.0.9-py3-none-any.whl
  web/website/build/wasm-app/assets/fhir4ds_v2-0.0.9-py3-none-any.whl
  web/website/static/wasm-app/fhir4ds_v2-0.0.9-py3-none-any.whl
  web/website/static/wasm-app/assets/fhir4ds_v2-0.0.9-py3-none-any.whl
  ```
  Wheels are `.gitignore`d, so this drift is invisible to `git status`. At runtime, the WASM demo will install **0.0.9** even though every docs page says 0.0.10.
- **Fix**: Copy `dist/fhir4ds_v2-0.0.10-py3-none-any.whl` into `web/wasm-demo/public/`, rebuild `web/wasm-demo` (`npm run build`), copy `web/wasm-demo/dist/` → `web/website/static/wasm-app/`, delete stale 0.0.9 wheels from all four locations. Add a Playwright assertion in `web/website/tests/demo.spec.ts` that the Pyodide-installed `fhir4ds.__version__` equals `0.0.10`.

### REV-PY-002 — `equivalence(1 year, 1 'a')` returns `True` but `equality()` returns `None` — HIGH
- **File**: `fhir4ds/fhirpath/engine/invocations/equality.py:171-200` (`_quantities_equivalent`)
- **Category**: MODEL_KNOWLEDGE (spec-semantics drift, C++/Python parity hazard)
- **Evidence**: `equality()` has a `_mixed_calendar_ucum_year_month` guard returning `None` per FHIRPath §6.1, but the new `_quantities_equivalent` helper lacks the same guard. Both units convert to the same base unit `'s' * 31556952`, so equivalence falls into the same-base-unit branch and returns `True`.
- **Fix**: Add the same `_mixed_calendar_ucum_year_month(left.unit, right.unit) -> None` guard at the top of `_quantities_equivalent`. Verify the C++ `fn_equivalent` has the same guard — otherwise this is also a native/Python parity gap.

### REV-PY-001 — `combine()` arity-2 accepts a `Boolean` argument but silently drops it — HIGH
- **File**: `fhir4ds/fhirpath/engine/invocations/__init__.py:52` and `combining.py:13-16`
- **Category**: MODEL_KNOWLEDGE / IDIOMATIC (spec-nonexistent API)
- **Evidence**: The arity table advertises `2: ["AnyAtRoot", "Boolean"]` for `combine(source, preserveOrder)`. This form does not exist in the FHIRPath spec — `combine()` is strictly arity-1. Worse, `preserve_order` is compared to `[]` rather than tested for truthiness, so callers passing spec-legal `false` or `true` both get plain list concatenation — the flag is silently dropped.
- **Fix**: Remove the bogus arity-2 entry: `"combine": {"fn": combining.combine_fn, "arity": {1: ["AnyAtRoot"]}}`. If a `preserveOrder`-style extension is needed internally, use a distinct private function.

### REV-REL-003 — Rebuilt WASM bundle was built against the wrong wheel — MEDIUM (consequence of REV-REL-002)
- **File**: `web/wasm-demo/src/workers/pyodide.worker.ts:58`; `web/website/static/wasm-app/fhir4ds-demo.js:1`
- **Category**: WASM_DRIFT
- **Evidence**: `pyodide.worker.ts` now loads `["micropip", "duckdb", "orjson", "pyarrow"]` (commit `9906e620`), and `fhir4ds-demo.js` was rebuilt (asset hashes changed), but because REV-REL-002 leaves 0.0.9 on disk, the rebuilt bundle was built against 0.0.9 imports. Resolves automatically once REV-REL-002 is fixed and the worker is rebuilt from a clean tree.

---

## Non-blocking findings (track for follow-up)

### CQL translator (3 MEDIUM, 3 LOW)
- **REV-CQL-001** (MEDIUM, `_core.py:823-950`): The `context.get_definition(name)` branch duplicates ref-resolution logic and hardcodes `_pt` — bypasses the `_classify_definition_ref` unification. Pre-existing (pre-0.0.10); tracked as parity-debt.
- **REV-CQL-002** (MEDIUM, `_core.py:952-1088`): Forward-reference branch has the same duplication and `_pt` hardcoding.
- **REV-CQL-003** (MEDIUM, `_core.py:740-744`): LIST-context JOIN shortcut drops the value-column case present in the qualified-identifier branch — perf gap, not correctness.
- **REV-CQL-004** (LOW, `_refstrategy.py:16-36`): `_RefKind` uses plain class instead of `Enum`; misleading performance justification comment.
- **REV-CQL-005** (LOW, `expressions/__init__.py:113-115`): Top-level import after module-level side-effecting call (`# noqa: E402`).
- **REV-CQL-006** (LOW, `expressions/__init__.py:484`): Forward-ref return type annotation (`"_RefStrategy"`) — resolved by REV-CQL-005.

### FHIRPath C++ extension (1 MEDIUM, 6 LOW)
- **REV-CPP-002** (MEDIUM, `parser.cpp:26-35`): `parseLongLiteralToken` calls `std::stoll` without catching `std::out_of_range`. A user-supplied Long literal like `99999999999999999999L` will crash the parser instead of returning `fhirpath_is_valid() = false`. Robustness regression for untrusted input.
- **REV-CPP-001** (LOW, `evaluator.cpp:2815-2836`): `trace()` second-arg projection discards result — intentional per §5.2.3, add clarifying comment.
- **REV-CPP-003** (LOW, `evaluator.cpp:6920-6935`): Unary Integer negation now returns 64-bit values; inconsistent with `toInteger()` 32-bit bounds. Confirm semantic change is intended.
- **REV-CPP-004** (LOW, `evaluator.cpp:87-95`): `readUtf8Codepoint` lacks defense-in-depth bounds check on `byte` index.
- **REV-CPP-005** (LOW, binary provenance): Bundled `fhirpath.duckdb.extension` (11.5 MB) has no `BUILD_PROVENANCE.txt` / hash manifest.
- **REV-CPP-006** (LOW, `evaluator.cpp:7566-7578`): `fn_isType` permissive default assumes `string` when both `actual_type` and `fhir_type` are absent — document in AGENTS.md.
- **REV-CPP-007** (LOW, `evaluator.cpp:1252-1271`): `normalizeEquivalentString` no longer collapses internal whitespace — intentional, matches Python.

### FHIRPath Python engine (2 HIGH already listed above, 4 MEDIUM, 3 LOW)
- **REV-PY-003** (MEDIUM, `udf.py:1652-1653`): `_needs_type_chain_rescue` triggers on legitimate `[False]` results — semantic confusion risk.
- **REV-PY-004** (MEDIUM, `udf.py:1628-1650`): `_resolve_core_type_chain` swallows `NotImplementedError` in non-strict mode — silently returns `[]` for unimplemented functions, masking gaps.
- **REV-PY-005** (MEDIUM, `udf.py:1583-1595`): `_resolve_trailing_choice_type_assertion` catches 8 exception types including `KeyError`/`AttributeError` — masks genuine evaluator bugs.
- **REV-PY-006** (MEDIUM, `invocations/logic.py:52-54`): `implies_op` evaluates `b_bool` eagerly before the `a_bool is False` short-circuit — breaks FHIRPath §5.2 short-circuit if `b` is malformed.
- **REV-PY-007** (LOW, multiple): Missing return-type hints on new public-ish APIs.
- **REV-PY-008** (LOW, `misc.py:236,249`): `FP_Date(...) and date_part` short-circuit idiom is opaque; validator helper is clearer.
- **REV-PY-009** (LOW, `udf.py:1460-1482`): `_CHOICE_SUFFIX_TO_FHIR_TYPE` duplicates `TypeInfo.SYSTEM_TO_FHIR_TYPE` — derive from model metadata instead.

---

## Per-dimension explicit notes

- **SQL injection**: None. All DuckDB SQL in scope uses static DDL, parameter binding, or `quote_identifier`-safe `SQLIdentifier(name=..., quoted=True)`. No new `con.execute(f"...")` patterns.
- **Hardcoded model knowledge**: None new in source logic. JSON additions (`terminology_property_defaults.json`, `_CHOICE_SUFFIX_TO_FHIR_TYPE`) are FHIR R4 spec properties or generated metadata. No resource-type branches like `if resource_type == "Observation"` introduced.
- **Redundant parsing**: None. `_parse_json` correctly avoids caching mutable dicts.
- **Error swallowing (HIGH)**: REV-PY-004 and REV-PY-005 catch broad exception sets in non-strict mode — documented above.
- **Type safety**: Minor — REV-CQL-006, REV-PY-007.
- **Idiomatic violations**: Minor — REV-CQL-004, REV-CQL-005, REV-PY-008.

## 0.0.10 special concerns — verification

- **CQL cross-library define references** (commit `3ad5d79b`): SHIPPED and usage-aware. SCALAR → correlated subquery with LIMIT 1; BOOLEAN/EXISTS → EXISTS; LIST → identity passthrough. No scalar-context leakage. Tests `test_cross_library_reference.py` and `test_definition_ref_parity.py` cover the matrix.
- **FHIRPath `is()` empty-collection fix** (commit `e0ee5119`): SHIPPED on both Python (`types.py:55-61`) and C++ (`fn_isType` at `evaluator.cpp:7471-7477`). Verified the referenced pytest PASSES.
- **FHIRPath choice-type parity** (commit `c90652f2`): SHIPPED. `primitive_shadow` propagated through `evalMemberAccess`, `fn_extension`, `fn_children`. Python uses `fhir_types_generated.CHOICE_TYPES` via `_get_choice_type_lookup()` with double-checked locking.
- **cql-server CLI docs**: SHIPPED and wired into sidebar (`sidebars.ts:93-96`).

## Files audited

- CQL: `fhir4ds/cql/translator/expressions/{__init__.py,_core.py,_property.py,_query.py,_refstrategy.py}`, `fhir4ds/cql/resources/terminology/terminology_property_defaults.json`
- C++: `extensions/fhirpath/src/fhirpath/{ast.hpp,evaluator.cpp,evaluator.hpp,lexer.cpp,lexer.hpp,parser.cpp,fhirpath_extension.cpp}`, `extensions/fhirpath/test/sql/fhirpath.test`
- Python: `fhir4ds/fhirpath/{duckdb/{udf.py,functions/math.py,function/string.py,evaluator.py},engine/{evaluators/__init__.py,invocations/*,nodes.py,util.py}}`
- Release: `pyproject.toml`, all `__init__.py`, `conformance/reports/dqm_report.json`, `docs/notebooks/*`, `web/{wasm-demo,website}/**`

No source files modified; review only. Detailed per-finding evidence in `.temp/review_{cql,cpp,py,release}_findings.md`.
