# Engineer Handoff — FP-15 HISTORIAN launch (2026-08-18)

Issues from qa_handoff.md: QA-001 (HIGH), QA-002 (MEDIUM), QA-003 (LOW INTENDED).

## QA-001 — `as` subclass semantics (HIGH) → INTENDED, change fully REVERTED
Implemented the spec-prose fix (§6.3 "type or subclass thereof") in both engines:
fallback `engine/invocations/types.py as_fn` (removed primitive-exact branch) and
native `fn_asType` (exact=false for JSON-valued operands; extension rebuilt).
The FHIRPath conformance suite then caught **testFHIRPathAsFunction11**
(934/935): official fixtures pin `as`/`ofType` as EXACT-match for FHIR
primitives (`gender.as(string)` EMPTY, `.as(code)` → male, `.as(id)` EMPTY)
while `is` is subtype-based (`gender is string` TRUE). Per GLOBAL_RULES,
fixtures outrank spec prose → REVERTED everything:
- types.py as_fn restored (primitive-exact branch, fixture citation added)
- evaluator.cpp fn_asType restored; extension rebuilt; redeployed binary is
  **byte-identical to the pre-launch original** (md5 d6043615…)
- FP-20 `as Element` empty-parity test and the `gender.as(string)` pin
  restored (docstrings now cite the fixture doctrine)
- New parity test `test_as_type_specifier_accepts_fhir_primitive_ancestors_fp15_historian`
  pins the is/as asymmetry on both engines (is subtype / as exact)
Recovery-gate lesson recorded: run the conformance suite BEFORE handoff — the
spec-verified change was fixture-wrong.

## QA-002 — fallback `implicitRules` typed string (MEDIUM) → RESOLVED
Root cause: `fhir4ds/fhirpath/models/r4/fhir_path_to_type.json` (engine path
metadata, mirrors fhir_model.py common mappings which already HAS it) lacked
`.implicitRules`; native `fhirFieldType` maps it → uri. Fix: added
`".implicitRules": "uri"` (data-driven). `implicitRules is FHIR.uri` now true,
`.type().name` = 'uri' on both engines. Regression test
`test_implicit_rules_typed_uri_both_engines_fp15_historian` (8 assertions).

## ENG-001 — choice-rescue clobbering (LOW hardening, ARCH-001) → RESOLVED
During QA-001 verification the udf.py choice-assertion rescues were observed
OVERRIDING a correct non-empty engine result (`parameter[0].value as
FHIR.string` → [] from the rescue while the engine returned the node) — the
exact ARCH-001 residual drift the SKEPTIC architect flagged. All op=`as` miss
paths in `_resolve_choice_type_assertion` and
`_resolve_trailing_choice_type_assertion` now return None (defer to engine)
instead of []. Behavior-neutral under the restored fixture doctrine; removes
the clobbering class permanently.

## QA-003 — abatementBoolean (LOW) → INTENDED (no change; documented)

## Validation
- fhirpath tree: **1916 passed** (was 1914 + 2 new fp15_historian tests).
- Full conformance: see architect phase rerun (ViewDefinition 144, CQL 1706,
  DQM 47 verified; FHIRPath rerun after revert confirmed 935/935 — final
  numbers in architect_handoff.md).
- Files changed: `fhir4ds/fhirpath/engine/invocations/types.py` (restored +
  citation), `fhir4ds/fhirpath/duckdb/udf.py` (guard-on-empty),
  `fhir4ds/fhirpath/models/r4/fhir_path_to_type.json` (+implicitRules),
  `fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py` (+2 tests,
  restored pins annotated), `fhir4ds/fhirpath/tests/unit/
  test_conformance_regressions.py` (pin restored + citation),
  `AGENTS.md` (FP-15 HISTORIAN section).
- No commits made; all changes in working tree.
