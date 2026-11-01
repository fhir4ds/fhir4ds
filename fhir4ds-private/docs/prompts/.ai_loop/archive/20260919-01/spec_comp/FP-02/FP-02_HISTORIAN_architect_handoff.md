# Architect Handoff — FP-02 HISTORIAN iteration 1 (2026-08-16)

## Golden Standard (invariants audited this iteration)
1. Native C++ and Python fallback MUST produce semantically identical FHIRPath results
   (display precision per the documented binary64-vs-Decimal convention).
2. Unit spellings between engines MUST be byte-identical on output channels.
3. Shared `ucum_units.hpp` stays byte-identical unless the CQL extension is rebuilt too.
4. `fhirpath_is_valid` doctrine: execution type errors valid; singleton/syntax invalid.
5. Fixes class-general (no expression-specific branches / test hacks).
6. CQL translation decoupled from FP_Quantity internals.
7. Rendering-pin updates must move TOWARD the N1-verbatim example values with inline
   justification (fixtures outrank prose; absent `<output>` = expected-empty).

## Audit verdict
- **Invariants 1/2 — HELD (empirically):** 158 dual-path probe cases → 0 parity failures;
  312 focused parity tests + 64 FP-02 family tests green; full fhirpath pytest
  **1702/1702**; full conformance **2832/2832** (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47) — baseline held.
- **Invariant 3 — HELD:** `git status` confirms `ucum_units.hpp` unmodified; the derived
  units live in a FHIRPath-local `FhirpathDerivedUnitTable()` in evaluator.cpp; CQL
  conformance 1706/1706 without rebuilding the CQL extension.
- **Invariant 4 — HELD:** no validity-classification paths changed; probes show
  is_valid=True on all new arithmetic/comparison surfaces (execution-type semantics).
- **Invariant 5 — HELD:** the four fixes are class rules — operand-term exponent merge,
  base-factor granularity selection with canonical tie-break, guard-set exemption for the
  exact-seconds duration family, curated table entries whose base forms go through the
  same sorted renderer as the multi-term reducer. No input-specific branches. The one
  mid-fix defect (V entries with A on the wrong side of the fraction) was caught by the
  canonical-spelling rule and corrected in both engines before final validation.
- **Invariant 6 — HELD:** no CQL source touched.
- **Invariant 7 — HELD:** 8 stale pins updated, each with inline N1/fixture justification;
  every equality-based pin (fixture testQuantity9, `= 36 'cm2'` family) survived unchanged.

## Structural notes (no action required)
- The dual-engine design keeps requiring mirrored logic (most-granular selection in
  math.py and evaluator.cpp; guard sets in compare() and
  isMixedCalendarUcumDurationAboveSeconds). The parity test suites are the compensating
  control and were extended (32 new cases).
- `fhir4ds/fhirpath/engine/invocations/math.py` shadows the builtin `abs` with the
  FHIRPath function — noted in AGENTS.md; future edits there must avoid builtin `abs`.
- Documented remaining gap (future launch, needs a coordinated dual-extension rebuild):
  Pa stays its own base dimension in the shared table, so `1 'Pa' * 1 'm2' = 1 'N'`
  remains empty.

## QA Enforcer Gate
HISTORIAN QA was sufficient: N1 normative HTML fetched and used to separate N1-pinned
from continuous/STU-only examples; official fixtures checked for every candidate finding;
158 pre-planned dual-path cases across 3 batteries; the prior launch's open §4.5
branch-1-vs-branch-2 question resolved with spec evidence (INTENDED); an environment
trap (stale site-packages import path) was diagnosed rather than mis-filed as 20 phantom
parity failures. No RETRY_QA.

## Issue ledger (all terminal)
- QA-001 MEDIUM RESOLVED — native ± Integer→Quantity('1') implicit conversion.
- QA-002 MEDIUM RESOLVED — operand-space composition + most-granular addition.
- QA-003 MEDIUM RESOLVED — calendar week/day/time vs UCUM ordering.
- QA-004 MEDIUM RESOLVED — curated derived-unit tables (Pa-composition gap documented).

## Loop control
Zero non-terminal CRITICAL/HIGH/MEDIUM issues remain; iteration 1 ≥ min_iterations (1);
exhaustive_mode false → **CLEAN EXIT** (exit_reason=CLEAN, workflow=null). State
hygiene performed: full details archived to ARCHIVE_LOG.md, issues tombstoned with
verified_in evidence.

## Recommended next steps (outer spec-comp orchestrator)
- Proceed to the FP-02 EXPLORER launch per the campaign rotation.
- EXPLORER targets worth probing: the Pa/pressure-dimension decomposition boundary
  (needs coordinated CQL+fhirpath rebuild if pursued), non-terminating most-granular
  conversions (e.g. `2 'mm[Hg]' + 3 'kPa'` rendering digits) for engine parity, and
  pathological unit spellings against the new derived tables.
