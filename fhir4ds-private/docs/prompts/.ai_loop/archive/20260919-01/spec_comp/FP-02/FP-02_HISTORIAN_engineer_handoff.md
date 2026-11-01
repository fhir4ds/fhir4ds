# Engineer Handoff — FP-02 HISTORIAN iteration 1 (2026-08-16)

## Triage
| ID | Severity | Category | Disposition |
|---|---|---|---|
| QA-001 | MEDIUM | PARITY_DIVERGENCE | RESOLVED (native ± implicit conversion) |
| QA-002 | MEDIUM | SPEC_VIOLATION (N1 §6.6.1/§6.6.2/§6.6.3) | RESOLVED (operand-space composition + most-granular ±, both engines) |
| QA-003 | MEDIUM | SPEC_VIOLATION (N1 §6.2/§5.5.7) | RESOLVED (calendar week/day/time ordering guard, both engines) |
| QA-004 | MEDIUM | SPEC_VIOLATION (N1 §6.1.1) | RESOLVED (curated derived-unit tables, both engines; one documented gap) |

## Fixes (all spec-grounded, mirrored in BOTH engines; extension rebuilt + redeployed twice)

### QA-001 — native `+`/`-` Integer→Quantity('1') implicit conversion
- `extensions/fhirpath/src/fhirpath/evaluator.cpp` (arithmetic block): `+`/`-` with one
  numeric and one Quantity operand now wraps the numeric via the existing
  `numericValueAsUnitQuantity()` helper before the Quantity±Quantity logic; `2 + 2 '1'`
  → `4 '1'`, `2 + 2 'cm'` still empty via base mismatch.
- `fhir4ds/fhirpath/engine/invocations/math.py`: the four numeric→Quantity wrap sites in
  `plus()`/`minus()` now use the canonical quoted unit `"'1'"` so both engines render
  `4 '1'` (was rendering `4 1` in the fallback after the most-granular change exposed it).

### QA-002 — operand-unit-space composition + most-granular addition
- `fhir4ds/fhirpath/engine/nodes.py` `__mul__`/`__truediv__`: merge RAW operand unit
  term-exponents and operate on operand values directly; mixed prefixes keep the ratio in
  the unit (`10 'cm.mm'`, `0.1 'cm/mm'` with `= 0.0001 'm2'` / `= 1` still true via base
  reduction). Base-conversion composition retained as the unparseable-unit fallback.
- `fhir4ds/fhirpath/engine/invocations/math.py` `_quantity_add_or_sub`: renders the result
  in the most-granular operand unit (smaller |base factor|; ties prefer the operand already
  in canonical/base form so `1 'm2/m' + 1 'm'` still gives `2 'm'`). NOTE: this module
  defines the FHIRPath `abs` function — magnitudes computed without the shadowed builtin.
- `evaluator.cpp` `*`, `/`, `±` branches mirrored (compose on operand units; most-granular
  selection identical).
- N1 examples now verbatim in both engines: `12 'cm' * 3 'cm'` → `36 'cm2'`,
  `3 'cm' * 12 'cm2'` → `36 'cm3'`, `12 'cm2' / 3 'cm'` → `4.0 'cm'` (.value 4.0/.unit cm),
  `3 'm' + 3 'cm'` → `303 'cm'`. Calendar additions now ALSO match the continuous build
  verbatim (`2 minutes + 60 seconds` → `180 seconds`, `1 'wk' + 2 days` → `9 days`,
  `3 'd' + 1 'wk'` → `10 'd'`, `1 week + 14 days` → `21 days`, `1 year + 12 'mo'` → `24 'mo'`).
- Official fixture testQuantity9 (`2.0 'cm' * 2.0 'm' = 0.040 'm2'` → true) verified green.

### QA-003 — calendar week/day/time keyword vs UCUM ordering
- `nodes.py` `FP_Quantity.compare()`: the mixed_calendar_ucum guard now exempts any pair
  inside `_weeks_days_and_time` (exact second multipliers), subsuming the old
  second/ms-only exemption; `evaluator.cpp` `isMixedCalendarUcumDurationAboveSeconds` gains
  the mirrored `isWeeksDaysTimeDuration` exemption.
- `1 day > 23 'h'` → true, `1 hour > 59 'min'` → true, `1 week > 1 'wk'` → false (equal,
  consistent with fixture testQuantity6 `7 days = 1 'wk'` → true); year/month keyword vs
  'a'/'mo' pairs stay empty (fixture-pinned).

### QA-004 — derived UCUM units
- `nodes.py` `_ucum_base_conversion_factor`: curated entries J/kJ, N/kN, W/kW/mW, A/mA,
  V/kV/mV with base forms matching the sorted renderer spelling (`'g.m2/s2'`, `'g.m/s2'`,
  `'g.m2/s3'`, `'g.m2/A.s3'`, `'A'`); multi-term reduction now expands term bases
  recursively so `kg.m2/s2`, `N.m`, `kg.m2/s3.A` reduce onto the same canonical strings.
- `evaluator.cpp`: FHIRPath-LOCAL `FhirpathDerivedUnitTable()` + `fhirpathFindUnitConversion()`
  (shared `ucum_units.hpp` untouched — CQL extension NOT rebuilt, per the byte-identity
  invariant); `convertQuantityToBase` direct + term lookups use it; direct-entry conversion
  is behavior-equivalent to the shared `ConvertToBaseUnit` (plain value×factor).
- `1 'kJ' = 1000 'J'`, `1 'J' = 1 'kg.m2/s2'`, `1 'N.m' = 1 'J'`, `1 'W' = 1 'kg.m2/s3'`,
  `1 'V' = 1 'kg.m2/s3.A'`, prefixes, equivalence and ordering all true in both engines.
- **Documented remaining gap:** Pa remains its own base dimension (decomposing it requires
  editing the shared table / rebuilding CQL), so `1 'Pa' * 1 'm2' = 1 'N'` stays empty.
  Flagged for a future launch that rebuilds both extensions.

## Regression tests
- NEW `test_quantity_arithmetic_spec_examples_both_backends_fp02_historian`
  (32 cases: QA-001 ±'1' family, QA-002 N1 examples + .value/.unit + calendar additions +
  fixture parity, QA-004 derived units) in `test_arithmetic_parity.py`.
- `test_comparison_parity.py` calendar test: week/day/hour/minute cases moved from empty
  to false/true with fixture grounding; added `1 day > 23 'h'`, `1 hour > 59 'min'`.
- 6 stale base-space pins updated with inline justification (spec-example direction):
  `36 'cm3'`/`4.0 'cm'`/`[{"value":36,"unit":"cm3"}]`/`12 'kg.m'`×2, cm/mm ±×/ pins
  (`20 'mm'`, `0 'mm'`, `10 'cm.mm'`, `0.1 'cm/mm'`).

## Validation (Recovery Gate)
- 158 dual-path probe cases (probe{,2,3}.py): **0 parity failures**.
- Focused parity suites (arithmetic/comparison/operator/literal/conversion): **312 passed**.
- FP-02 family tests: 64 passed.
- Full fhirpath package pytest + full conformance (2832 baseline): see architect handoff
  for final numbers (runs completed post-handoff; blocker if below baseline).

## New issues discovered during fix
- None beyond the documented Pa-composition gap (noted inside QA-004's resolution).
