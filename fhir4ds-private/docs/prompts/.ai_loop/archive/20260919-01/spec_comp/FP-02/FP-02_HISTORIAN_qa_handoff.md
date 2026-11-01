# QA Handoff — FP-02 HISTORIAN (iteration 1, 2026-08-16)

## Chunk
FHIRPath §4.2 Operators (equality, comparison, arithmetic incl. collection operands and
type-error behavior, `|` union, and/or/xor/implies, is/as), §4.3 Function Invocations,
§4.4 Null/Empty propagation, §4.5 Singleton Evaluation of Collections.

## Method (HISTORIAN: spec-compliance walk + institutional memory)
- Spec grounding: local cached continuous-build spec + **fetched N1 normative HTML**
  (`https://hl7.org/fhirpath/N1/`) to separate N1-pinned examples from continuous/STU-only
  text; official R4 fixtures (`tests-fhir-r4.xml`) checked for every candidate finding
  (fixtures outrank spec prose — FP-01 lesson).
- 158 dual-path probe cases across 3 batteries
  (`/mnt/d/fhir4ds/.temp/qa/fp02_historian_2026_08_16/probe{,2,3}.py`):
  101 §4.2–§4.5 walk + SKEPTIC-fix regression anchors, 31 derived-unit/calendar/N1-example
  scoping, 26 calendar-comparability matrix + Integer+Quantity('1') family.
- **Environment catch:** `python3 <script>.py` from `.temp/qa/` imports the STALE
  site-packages `fhir4ds` (script dir on sys.path, not cwd) while the native extension
  there was redeployed — producing phantom "fallback lost the fix" parity failures.
  All probes must run with `PYTHONPATH=/mnt/d/fhir4ds`. With repo source: **0 parity
  failures in battery 1**; all 4 SKEPTIC fixes (QA-001..QA-004 of that launch) re-verified
  green and regression-free.

## SKEPTIC's open §4.5 question — RESOLVED as INTENDED
The conversion table shows Integer/String→Boolean is **Explicit**, so §4.5 branch 1 never
fires for Boolean contexts; branch 2 (single non-Boolean node → true) always applies. The
spec's own iif examples pin it: `iif(1,...)`/'iif(0,...)'/'iif('hi',...)' → then-branch
("0 is a non-empty single item, not a Boolean false"). Repo behavior (`zero and true` →
true, `boolText('false') and true` → true, `iif(boolText,'y','n')` → 'y') is spec-correct
in both engines. No issue.

## Issues logged (evolution.json)
1. **QA-001 (MEDIUM, parity)** — native `+`/`-` misses the Integer/Decimal→Quantity('1')
   implicit conversion: `2 + 2 '1'` → native empty vs fallback `4 '1'` (5 repros;
   `2 * 2 '1'` / `2 / 2 '1'` work natively — internal inconsistency). Root: evaluator.cpp
   mixed Quantity/numeric branch handles only `*`/`/`.
2. **QA-002 (MEDIUM, spec, both engines)** — quantity arithmetic composes in base-unit
   space instead of the spec's operand-term merge / most-granular unit. N1 examples:
   `12 'cm' * 3 'cm' // 36 'cm2'` → repo `0.0036 'm2'`; `3 'cm' * 12 'cm2' // 36 'cm3'` →
   `0.000036 'm3'`; `12 'cm2' / 3 'cm' // 4.0 'cm'` → `0.04 'm'` (`.value` 0.04);
   `3 'm' + 3 'cm' // 303 'cm'` → `3.03 'm'`. Semantic equality holds everywhere;
   official fixture testQuantity9 unaffected. SKEPTIC rendering pins to update at
   test_arithmetic_parity.py:1198-1199, 839.
3. **QA-003 (MEDIUM, spec, both engines)** — calendar week/day/time keyword vs UCUM time
   ORDERING empty while equality works: `1 day > 23 'h'` empty but `1 day = 24 'h'` true;
   also `1 hour > 59 'min'`, `1 minute > 59 's'`, `1 week > 6 'd'`; yet `1 month > 29 'd'`
   true. 4th instance of the equality/ordering conversion-surface family. Root:
   `FP_Quantity.compare()` mixed_calendar_ucum whitelist (nodes.py) +
   `isMixedCalendarUcumDurationAboveSeconds` (evaluator.cpp).
4. **QA-004 (MEDIUM, spec, both engines)** — derived-unit conversion gaps: `1 'kJ' = 1000 'J'`
   empty (prefix scaling works for base units), `1 'J' = 1 'kg.m2/s2'`, `1 'N.m' = 1 'J'`,
   `1 'Pa' * 1 'm2' = 1 'N'` empty; ordering/equivalence too. J/N/W/V (+A) missing from the
   tables while derived pressure (Pa/mm[Hg]) is present.

## Verified clean (negative results worth keeping)
- §4.5 spec examples verbatim (`iif(1/0/'hi')`, node criteria, `iif({},...,'n')`); multi-item
  errors → empty; `(1|2) + 3` invalid singleton.
- is/as walk: System.* specifiers, temporal literals, quantity is/as, `as` type-assertion
  (no conversion: `1 as Decimal` → empty), empty/multi-item propagation — all correct,
  both engines.
- §6.1.1 `nums = 1` → false correct ("different number of items → false"); `23 = 23 '1'`
  → true (N1 example).
- §6.6.1/§6.6.2 continuous-build examples that pass: `10 'm/s' * 10 's'` → 100 'm',
  `120 'm' / 60 's'` → 2.0 'm/s', `3 * 2 'cm'` → 6 'cm', `60 's' / 2` → 30 's',
  `2 + 2 'cm'` → empty, `10 'mg' / 2 'mg'` → 5.0 '1', dimensionless '1', `.value` free of
  binary64 drift on new composition sites, `(1 'm' | 100 'cm').count()` = 1 dedup.
- Calendar arithmetic VALUES via unanchored factors are N1-defensible (`2 minutes + 60
  seconds` → 180 's'); continuous-build-only divergences documented as observations, no
  action: `12 day * 45 'm'` → `46656000 'm.s'` (continuous says empty), `1 year + 12 'mo'`
  → seconds (continuous says empty), calendar result units render UCUM 's' not 'seconds',
  `60 / 1 's'` renders '1/s' not '/s'.

## FIX anchors
- QA-001: evaluator.cpp `// Quantity * number or number * quantity` block — accept `+`/`-`
  by converting the numeric operand to Quantity unit '1' and delegating to the
  Quantity±Quantity path ('1' vs 'cm' still empty via base mismatch).
- QA-002: compose units from the OPERAND unit term-exponents (no prefix→base scaling of
  values; mixed prefixes → 'cm.m' which equality still reduces per fixture testQuantity9);
  `+`/`-` convert to the most-granular operand unit (smaller base factor). Mirror Python
  `__mul__/__truediv__/__rtruediv__/__add__/__sub__` and native compose/± sites; update
  the 3 SKEPTIC rendering pins to spec-verbatim expectations.
- QA-003: in `compare()` / `isMixedCalendarUcumDurationAboveSeconds`, allow mixed
  calendar-keyword↔UCUM pairs where BOTH sides are week/day/time (exact seconds via
  datetime multipliers / UCUM table); keep 'mo'/'a' mixed pairs empty.
- QA-004: add curated derived-unit entries (J, kJ, N, W, V, kW/mW/kN/mV/kV, A, mA) mapping
  to multi-term base forms in nodes.py table and the FHIRPath-side C++ surface (do NOT
  touch shared ucum_units.hpp — CQL extension stays unrebuilt).
