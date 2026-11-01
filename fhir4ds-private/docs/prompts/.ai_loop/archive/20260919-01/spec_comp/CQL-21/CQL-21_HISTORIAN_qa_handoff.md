# QA Handoff — CQL-21 (Clinical Operators), HISTORIAN, iteration 1

## Spec anchors
CQL 1.5 Appendix B (Age/AgeAt/CalculateAge/CalculateAgeAt = duration calculations;
sub-precision birthDate/asOf → uncertainty interval; Integer-typed results),
In (list) equality semantics, Min/Max list aggregates, Negate, binary Max with
implicit conversion. Verified against the live 2019May spec text used by the
prior SKEPTIC pass (chunk archive spec_comp/CQL-21/).

## Environment repair (pre-test)
Site-packages cql.duckdb_extension was the STALE pre-rebuild binary (19:56,
md5 61d8b2c1) — the SKEPTIC's site-packages deployment did not persist.
Redeployed repo bundle (md5 82b234168290f6a6053b583d70e3d9d6) to site-packages.
No ~/.duckdb stale cache present.

## What was probed (new, vs SKEPTIC's pass)
1. Direct UDF uncertainty semantics, all 7 precisions, partial birthDate AND
   partial asOf, uncertain-negative, crisp-negative→null, null propagation,
   py vs native: **all conformant and parity-OK** (cql21_h1.py).
2. Translator lowering of age into every generic context: comparisons
   (cqlUncertainCompare ✓), interval-in ✓, between ✓, uncertainAdd/Multiply ✓,
   is null ✓, AgeInHours Now()/Today() split ✓, two-arg resource form ✓.
3. **NEW divergences** — post-uncertainty VARCHAR age meeting lowerings that
   were never updated (probes cql21_h2/h3/h4 + end-to-end population run):
   - **QA-001 HIGH**: `age in {9,36}` with crisp age 36 → **False** (silent
     wrong result; CQLListContainsEq INTEGER literals vs VARCHAR age). py+cpp.
   - **QA-002 MEDIUM**: `Min({age, age})` over crisp ages {36,8} → **27**;
     list_min/list_max lexicographic over VARCHAR. py+cpp.
   - **QA-003 MEDIUM**: `-age` and `Max(age, 30)` → BinderException
     (valid CQL → non-binding SQL). py+cpp.
4. Terminology spot checks: code/concept equal/equivalent, In(ValueSet)
   including null-code→false, ExpandValueSet count — routed through the
   existing parity suite (16/16 pass) + direct in_valueset/ExpandValueSet
   probes: conformant, no new divergence.
5. Regression: full test_clinical_operator_parity.py 16/16 pass on current
   tree (py + native). DQM hard regression probe deferred to the FIX-phase
   gate (master validation, incl. DQM 47).

## Carried forward
- QA-004 (DEFERRED, from SKEPTIC launch): boolean-define-alias collision
  (`define F: Patient.active; F and true` → TranslationError), pre-existing,
  owned by list/property-typing chunk.

## Reproducers
`.temp/qa/cql21_h1.py` … `cql21_h5.py` + end-to-end population snippet in
handoff evidence (evolution.json issues[]).

## Recommended fix shape (root cause, not shims)
In the translator, extend uncertainty-capable operand detection to the
remaining generic lowerings: (1) `in {list}` → OR of cqlUncertainCompare '='
(or typed cast of elements); (2) unary '-' on uncertain operand →
cqlUncertainMultiply(x, '-1'); (3) binary Max/Min with an uncertain operand →
cast literals to VARCHAR and use cqlUncertainCompare-based selection (or
cqlUncertain-aware greatest/least); (4) list Min/Max over uncertain elements →
numeric-aware comparison (interval-aware min/max per §22.21: min of lows /
max of highs). All changes dual-engine lockstep + parity tests in
test_clinical_operator_parity.py.
