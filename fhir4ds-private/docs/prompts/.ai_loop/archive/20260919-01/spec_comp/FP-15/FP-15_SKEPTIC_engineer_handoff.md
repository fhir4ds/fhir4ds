# Engineer Handoff — FP-15 fresh SKEPTIC launch, iteration 1 (2026-08-18)

All 5 open issues RESOLVED (QA-006 was pre-classified INTENDED). Fixes are
spec-grounded, minimal, and land in BOTH engines where required by the
dual-engine lockstep rule.

## Fixes

1. **QA-001 (HIGH)** — `fhir4ds/fhirpath/engine/nodes.py`
   `TypeInfo.FHIR_TYPE_HIERARCHY` now merges canonical `type2Parent.json`
   OVER legacy `fhir_type_hierarchy.json` (which flattened uuid/oid straight
   to string and erased the uri ancestor). Documented conventions preserved
   as explicit overrides: `uri→string`, `Money→Quantity`,
   `Dosage/Timing→Element`. Restores fixture testTypeA4
   (`valueUuid is FHIR.uri` // true) on the Python fallback surface.
2. **QA-002 (HIGH)** — `extensions/fhirpath/src/fhirpath/evaluator.cpp`
   `fn_isType` literal-Quantity branch now requires `!explicit_namespace`, so
   `5 'mg' is FHIR.Quantity` → false (namespace doctrine, testType12/14),
   while unqualified `is Quantity` keeps the shared true convention.
   Extension REBUILT (`make fhirpath_loadable_extension`) and REDEPLOYED to
   `fhir4ds/fhirpath/duckdb/extensions/` and
   `extensions/fhirpath/build/release/repository/v1.5.2/...` (md5 cf28ee2c…).
   NOTE: the first background build raced the source edit and produced a
   stale binary — a forced recompile after `touch` landed the fix.
3. **QA-003 (HIGH)** — `fhir4ds/fhirpath/duckdb/udf.py`
   `_get_choice_type_lookup()` now skips single-option CHOICE_TYPES entries
   (mirrors `fhir_model.py`), so `Resource.contained`/`Observation.subject`
   etc. are no longer treated as choice fields; the choice-assertion rescue
   no longer hijacks `contained is/as(T)` (and Reference-only fields).
4. **QA-004 (MEDIUM)** — `fhir4ds/fhirpath/duckdb/functions/typecheck.py`
   Exported `is_type`/`as_type` string specifiers now resolve namespaces like
   the engine parser (distinct unqualified System names → System; others →
   FHIR; qualified/backtick parsing). `5 as Integer` → `[5]` (11th instance
   of the "exported helper API forgotten" family).
5. **QA-005 (LOW)** — `fhir4ds/fhirpath/duckdb/udf.py`
   New `_INVALID_TYPE_SPECIFIER_INVOCATION` precheck, applied to
   string-masked text at both `_get_compiled_evaluator` and
   `fhirpath_is_valid_udf`: rejects function invocations chained onto `is`/`as`
   type specifiers (`X is FHIR.Quantity.not()`), matching the native grammar
   rejection; no false positives on valid is/as forms (guarded in tests).

## Verification
- Regression tests appended to
  `fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py`
  (5 tests, `*_fp15_skeptic2`): 31/31 in file.
- Full 121-case dual-path probe rerun: **0 parity diffs**.
- Full fhirpath pytest tree: **1914 passed**.
- Conformance: **2832/2832** (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47) —
  baseline held.

No new issues discovered during fixing.
