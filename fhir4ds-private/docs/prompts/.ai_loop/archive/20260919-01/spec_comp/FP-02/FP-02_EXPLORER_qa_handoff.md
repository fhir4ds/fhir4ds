# FP-02 EXPLORER — QA Handoff (2026-08-16, spec-compliance campaign)

**Personality**: EXPLORER (Role C — Fuzzer/Abuser). Third personality on chunk FP-02
(§4.2 Operators, §4.3 Function Invocations, §4.4 Null/Empty, §4.5 Singleton Evaluation).
Prior launches: SKEPTIC (4 fixed), HISTORIAN (4 fixed).

## Probe inventory

- `.temp/qa/fp02_explorer_2026_08_16/probe.py` — 162 cases, 7 batteries (B1 precedence
  corners incl. unary polarity vs binary ops; B2 implies truth-table edges with
  empty-from-field/non-Boolean-singleton/multi-item antecedents; B3 heterogeneous
  collection equality; B4 union dedup; B5 null/empty propagation through nested
  invocations; B6 singleton multi-item comparisons; B7 type-error vs empty
  distinctions). 1 parity fail.
- `.temp/qa/fp02_explorer_2026_08_16/probe2.py` — 74 cases, 10 batteries (and/or/xor
  empty corners + short-circuit; implies associativity discriminator; iif multi-item
  focus/criterion; unary polarity corners; `&` coercions; not() singleton Boolean;
  is/as multi/empty; combine vs union dedup; cross-type equality vs ordering;
  extraction-then-compare). 0 parity fails.
- Ad-hoc dual-path drill probes: aggregate-registry matrix (sum/min/max/avg × 11
  expressions), boolean-ordering is_valid matrix (13 expressions), field-vs-literal
  `is` matrix (25 expressions), temporal-field `is` matrix (issued/authoredOn/date/
  birthDate/effectiveDateTime/unknown-shape fields, ~30 evaluations).

All probes run with `PYTHONPATH=/mnt/d/fhir4ds` (stale site-packages trap).

## Verified clean (negative results, both engines, parity + spec)

- **Precedence (§6.8)**: `2 * -3`=-6, `1 + -1`, `1 - -1`, `-2 + 3`=1, `- -1`,
  `10-2-3`, `10/5/2`, `2+3*4-1`; `&` tighter than `|`; `is` tighter than `|`;
  and tighter than or/xor; xor tighter than implies; implies LEFT-associative
  (discriminator `{} implies false implies {}` -> empty); `=` lower than `|`;
  `-3.abs()`=-3 vs `(-3).abs()`=3; `-2.pow(3)` unknown-function (pow not R4).
- **implies truth table**: all 9 fixture corners reproduced with MISSING-FIELD and
  JSON-null empty operands; §4.5 branch-2 non-Boolean singleton antecedents
  (`zero/1/boolText/gender implies ...`); multi-item antecedent -> empty.
- **and/or/xor three-valued tables**: all fixture corners incl. `{} and false`=false,
  `{} or true`=true short-circuits.
- **Empty/`&`**: `'x' & {}`='x', `{} & {}`='', `{} & 1`='1' (fixtures C2/C3/C4);
  `(1|2|3) & 'b'` empty + is_valid False (execution singleton violation).
- **Collection semantics**: `{}`-only literal grammar (multi-element `{1,2}` is NOT
  FHIRPath syntax — correctly rejected by both engines; `|` is the constructor);
  union dedup cross-type/decimal/temporal/nested; `combine` preserves duplicates
  (6); `distinct` 2; ordered `=` vs unordered `~` incl. duplicates via field dups.
- **Null propagation**: fixture-backed `{}.iif(true,'a','b')`='a' (testIif7 — iif on
  empty focus evaluates); empty args (substring({},1) empty; substring(1,{}) 'bc');
  lazy iif does not raise dormant type errors; allTrue({})=true / anyTrue=false /
  count=0 / max/min empty; trace passthrough.
- **Singleton evaluation**: `nums = 1`=false, `nums != 1`=true, `nums < 3` empty,
  `(1|2)+1` empty + is_valid False (field-backed multi-item stays is_valid True);
  `nums.iif(true,1,2)` empty (testIif10 analog); first()/last() extraction OK.
- **Type errors vs empty**: `'a'-'b'`, `1+'a'`, `true+1`, `'a'*2` -> empty +
  is_valid True; `1/0`, `1 div 0`, `1 mod 0` -> empty (fixtures Div5/Mod5);
  cross-type `=`/`~` empty/false as pinned (`1 ~ true`=false).
- **is/as typing per fixtures**: `t is Boolean`=false / `t is FHIR.boolean`=true /
  `t.is(boolean)`=true / `t as Boolean`=empty — CORRECT per testType11-14 (FHIR
  primitives are FHIR types, not System types); model-known fields
  (birthDate/effectiveDateTime/valueQuantity) correct on both engines.

## Issues filed (see evolution.json)

- **QA-001 MEDIUM (parity, §4.3)**: fallback engine registry implements non-N1
  `sum`/`min`/`max`/`avg`; native -> unknown/empty. `{}.sum()`->0 in fallback even
  violates the empty-input convention; is_valid=False on both while fallback
  evaluates. Fix direction: remove the 4 registry entries (direct-helper API in
  functions/math.py is separate and unaffected).
- **QA-002 MEDIUM (parity + spec, §6.3 via §4.2 is/as)**: native fn_isType lexical
  shape-sniffing for date/dateTime (evaluator.cpp:9848, 9867) vs fallback
  model-driven typing. Unknown date-shaped fields diverge; REAL fields
  (authoredOn, issued, Composition.date) are spec-wrong in one or both surfaces
  (authoredOn is string->true both; issued typed dateTime natively/instant in
  fallback; authoredOn is dateTime false in fallback). Metadata mechanisms also
  differ (native hardcoded fhirFieldType table vs models/r4/fhir_path_to_type.json).
  Fix direction: remove native sniffing; align canonical metadata on both sides
  with R4 element types (authoredOn=dateTime, issued=instant, date=dateTime);
  requires extension rebuild.
- **QA-003 LOW (is_valid classification)**: boolean-vs-boolean ordering
  (`true > false`) classified is_valid=False on both while the same execution-error
  class with mixed types is True. Message missing from
  `_is_valid_empty_result_error` (udf.py:2393) and the native accept list
  (fhirpath_extension.cpp:1878-1880). Requires native rebuild (shares QA-002's).

## Notes for FIX

- QA-002 native rebuild also covers QA-003's native side; one rebuild+redeploy cycle.
- Do NOT "fix" `t is Boolean`->false or `authoredOn is string`-style System-vs-FHIR
  namespace answers — fixtures pin the namespace split (testType12/14).
- `fhirFieldType` (native, evaluator.cpp:3025) and fhir_path_to_type.json are the
  two canonical metadata surfaces to align; broader R4 temporal-field coverage is a
  follow-up data task, not this launch.
