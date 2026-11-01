# QA Handoff — FP-08 EXPLORER (iteration 1, 2026-08-17)

Chunk: FHIRPath §5.5.7 Quantity Conversion, §5.5.8 String Conversion,
§5.5.9 Time Conversion. Personality: EXPLORER (boundary/combination probing).

## What was probed
95 dual-path cases (native C++ extension vs forced Python fallback; probe at
`/mnt/d/fhir4ds/.temp/qa/fp08_explorer3_2026_08_17/probe.py`):

- **A. toString extremes**: 32-bit max Integer, 28-digit Decimals,
  `(-0.0)`, int-overflow literal, negative quantities, negative Decimal
  quantities, all 8 calendar keyword spellings (singular/plural), Time at
  every precision incl. offset-suffixed, DateTime with Z / +05:30 offsets,
  partial precisions, leap-second-adjacent `.999`, booleans, derived units,
  exponent units, empty/multi-item/resource/collection inputs.
- **B. convertsToString corners**: every literal type, empty, multi-item,
  Quantity, temporals, resource objects.
- **C. toQuantity convert→convert roundtrip chains**: m↔cm↔m, kg↔g↔kg,
  year↔day↔year, year→month→day (360-day doctrine), month→week→day,
  J/kJ, N/kN, W/kW families, kJ→kg.m2/s2, m2↔cm2, negative quantities,
  exact metric chains, h↔min↔s roundtrip, incompatible chains, calendar
  week/day roundtrips.
- **D. convertsToQuantity arity/invalid forms**: no-arg, Integer/Boolean/
  empty-string/Quantity unit args, two args, bogus units, string quantity
  input forms.
- **E. toTime edges**: dateTime-shaped strings (with/without Z/offset),
  T-prefixed partial times with offsets, offset+fraction combos, dateTime
  literals, empty/multi-item, convertsToTime full matrix.
- **F. Converted values feeding equality/ordering/arithmetic/membership/
  distinct/.value/toString** from earlier chunks.

## Findings
- **QA-001 (HIGH, parity)**: fallback `conv_unit_to` never converted
  direct-table-key units — `(1000 'J').toQuantity('kJ')` → `[]` vs native
  `1 'kJ'`; also N/W/V families, `m2`↔`cm2`, `kJ`→`kg.m2/s2`, and their
  convertsToQuantity forms (false vs true). Root cause: base-reduction
  fallback guarded on `_unit_reduces_to_base()`, which returns False for
  direct `_ucum_base_conversion_factor` keys.
- **QA-002 (MEDIUM, parity)**: non-terminating metric conversions rendered
  15-sig-digit binary64 natively vs 28-sig-digit Decimal in the fallback
  (`(1 'kPa').toQuantity('mm[Hg]')`).
- **QA-003 (LOW, INTENDED)**: empty-string unit arg acts as the no-arg form
  in BOTH engines (shared convention; `' '` correctly rejected).

## Verified clean (do not "fix")
- `(-0.0).toString()` → `0.0` both engines (FP-01 QA-005 doctrine).
- `(0.001 'kg').toQuantity('mg')` → `1000 'mg'` (arithmetically correct).
- `'180 cm'.toQuantity()` / `'5 mg'.toQuantity()` → empty both engines
  (bare UCUM codes in strings are not parsed; only calendar keywords and
  quoted units — SKEPTIC case-sensitivity doctrine).
- toString/convertsToString empty/multi-item doctrine, resource toString,
  toTime full grammar matrix (dateTime strings, offsets, partials),
  converted-value equality/ordering/arithmetic/membership, is_valid
  behavior — zero parity diffs.
- Doctrine guards after fixes: `1 year -> 's'` empty, `1 'month' = 1 'mo'`
  empty, `(1 'kg').toQuantity('m')` empty, `(1 'Cel').toQuantity('K')`
  empty — all preserved in both engines.

Environment notes honored: PYTHONPATH=/mnt/d/fhir4ds, LOAD by absolute
path, `register_fhirpath(con) is False` assertion on fallback.
