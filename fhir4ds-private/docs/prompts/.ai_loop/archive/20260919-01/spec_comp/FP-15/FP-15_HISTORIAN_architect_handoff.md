# Architect Handoff — FP-15 HISTORIAN launch (2026-08-18, iteration 1)

## Iteration compression (QA → FIX → ARCHITECT)
HISTORIAN QA ran a fresh 78-case dual-path probe plus 6 targeted drills on
§6.3 `is`/`as` (infix + functional, native + forced fallback), re-verified all
5 SKEPTIC fixes regression-free, and filed 3 issues. Remediation: QA-002
(fallback `implicitRules` → FHIR.string vs native uri) fixed via a missing
`.implicitRules: uri` entry in `models/r4/fhir_path_to_type.json`; QA-001
(dual-engine `as` primitive exactness vs §6.3 prose) was implemented as a
subtype fix in BOTH engines, then the FHIRPath conformance suite caught
official fixture testFHIRPathAsFunction11 (934/935) pinning `as` as EXACT for
FHIR primitives — the change was fully reverted (redeployed native binary
byte-identical to pre-launch, md5 d6043615), QA-001 reclassified INTENDED
with the is/as asymmetry now explicitly parity-pinned; the recovery gate
worked as designed. ENG-001: the udf.py choice-assertion rescues were
observed clobbering a correct non-empty engine `as` result (SKEPTIC
ARCH-001 residual drift) — all op=`as` miss paths now defer (None) instead of
returning []. QA-003 (abatementBoolean on non-R4 input) documented INTENDED.

## Golden-standard invariants exercised
1. Fixtures outrank spec prose (GLOBAL_RULES) — enforced by the suite.
2. Dual-engine changes land in lockstep with a native-vs-fallback parity
   test — done (2 new `*_fp15_historian` tests in test_type_parity.py).
3. After evaluator.cpp changes, rebuild + redeploy the bundled extension and
   verify through the reloaded binary — done (stale-binary trap avoided; the
   first native patch attempt missed the operative exact-flag branch and was
   caught by exactly this verify-before-concluding discipline).
4. Model knowledge is data-driven — the implicitRules fix is a metadata entry,
   not a code branch.

## New architectural finding (logged, not fixed)
- **ARCH-002 (MEDIUM, drift):** field-name→primitive-type knowledge lives in
  THREE curated copies that can diverge: native `fhirFieldType`
  (evaluator.cpp), `fhir_model.py:_get_common_path_to_type_mappings`, and the
  engine-side `models/r4/fhir_path_to_type.json`. QA-002 was an instance of
  this drift (2 of 3 had `implicitRules`; the engine JSON did not).
  Recommended: generate `fhir_path_to_type.json` (or the engine mapping) from
  a single source. Logged in AGENTS.md Architecture Drift Log.
- Confirmed persistent (pre-existing, no action this launch): udf.py choice
  rescues remain regex-based heuristics layered over the engine; guard-on-empty
  now bounds their blast radius, but full deletion requires engine-side choice
  coverage for all CHOICE_TYPES fields.

## QA Enforcer Gate
QA was NOT lazy: fresh angles (multi-level ancestors, false-vs-empty,
string-arg forms, real choice fields, namespace crosses), reproducer probes
archived, spec verified by web fetch, and institutional memory used to
re-verify the SKEPTIC fixes. One process lesson (recorded): the §6.3 fixture
grep missed FUNCTION-form spellings (`as(string)`), which cost one
implement-revert cycle; the conformance recovery gate caught it. No veto:
RETRY_QA stays false.

## Validation evidence
- fhirpath tree: 1916 passed (includes 2 new fp15_historian tests)
- viewdef+cql+dqm+root tests: 6938 passed, 9 skipped
- Full conformance: **2832/2832** (ViewDefinition 144, FHIRPath 935,
  CQL 1706, DQM 47) — baseline held
- Native extension rebuilt twice; final deployed binary identical to
  pre-launch (revert verified by md5)

## Recommended Fix Order (next launches)
1. ARCH-002 metadata consolidation (single source for field-name typing).
2. Engine-side choice resolution completeness → then delete udf rescues.
3. Nothing else open from this chunk: FP-15 §6.3 is/as is clean.
