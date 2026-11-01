# QA Handoff — FP-07 EXPLORER (launch 3, iteration 1, 2026-08-17)

Chunk: FHIRPath §5.5.4 Date Conversion, §5.5.5 DateTime Conversion, §5.5.6
Decimal Conversion — toDate/convertsToDate/toDateTime/convertsToDateTime/
toDecimal/convertsToDecimal. Personality: EXPLORER (adversarial chaining).

## What was probed (123 fresh dual-path cases)

Probes: `/mnt/d/fhir4ds/.temp/qa/fp07_explorer3_2026_08_17/probe{,2}.py`
(native extension conn asserting `register_fhirpath(...) is True` vs forced
Python fallback, both via `SELECT fhirpath(?, ?)`; PYTHONPATH=/mnt/d/fhir4ds).

Surfaces briefed for this launch, none previously covered by SKEPTIC/HISTORIAN:

1. **Converted temporals as ±/arithmetic operands** (both operand orders,
   quantity+converted-date), partial-precision arithmetic (`'2015'.toDateTime()
   + 1 year`, `'2015-02' + 4 days` → month-precision truncation, consistent
   with the pinned `@T14 + 30 'minutes'` §6.7 doctrine), leap/non-leap day
   adds, date-minus-date duration, offset/millisecond arithmetic crossing
   midnight in Z and ±hh:mm spellings.
2. **convertsTo\* feeding iif()/where()/select()** — string and resource-field
   criteria, empty and multi-item criteria (error → empty, matching the pinned
   multi-item doctrine), defineVariable interplay inside iif branches.
3. **Roundtrips across precisions/offsets** — `toDateTime().toDate().
   toDateTime()` yields day precision `2015-02-04T` (time loss), `Z`/offset
   spellings preserved through conversion, precision-mismatched equality
   correctly empty.
4. **toDecimal at the 28-sig-digit ROUND_HALF_EVEN boundary × FP-01 exact
   arithmetic** — `'0.1'.toDecimal() + 0.2 = 0.3` true, exact text at 28/29
   digits, scale-preserving add (`'0.10'+'0.20'`→`0.30`), 28-digit division
   guard digit (`'2.0'/3`→`0.6666666666666666666666666667`), half-even
   `.round()`, `-0.0` normalization, converted-decimal ÷ converted-decimal.
5. **Extension-value fields & nested paths** — `extension.where(url=...).
   value{Date,DateTime,Decimal,Integer}` conversions + arithmetic, `contained`
   resources, `contact.period.start`, multi-`component.valueString` where/
   select chains.
6. **Multi-item collections** — toDate/toDecimal/convertsTo* on multi-item →
   empty/error in both; `.first()`, `.select($this.toDecimal() * 2)` chains.
7. **Equality/ordering doctrine** — converted temporals/decimals vs literals,
   cross-offset equality, partial-precision ordering → empty, Decimal↔Integer
   and Decimal↔Quantity('1') equality/ordering (`'5' < 6 '1'` → empty in both
   engines: shared convention).
8. **is_valid parity** on 8 chained/arity variants (all agree).

## Findings

- **QA-001 (MEDIUM, CONFIRMED → fixed in FIX phase): fallback temporal
  arithmetic re-rendered authored `Z` as `+00:00`.**
  `@2020-06-30T23:59:59Z + 1 second` → native `2020-07-01T00:00:00Z` vs
  fallback `2020-07-01T00:00:00+00:00` (also `- 1 second`, `+ 1 minute`,
  millisecond precision, `+ 0 seconds` identity, and `.toDateTime()`-converted
  operands). Plain conversion and equality were correct in both engines; only
  arithmetic result display diverged. No official fixture pins Z-suffixed
  arithmetic output → engine parity governs (§5.5.1 keeps `Z` for UTC).

Zero other parity diffs; zero spec violations. All remaining probe "BAD"
lines are probe-harness expectation formatting (multi-item JSON list display)
or previously pinned doctrines.

## NOT A BUG pins (both engines agree; do not "fix")

- `2 days + '2015-02-04'.toDate()` → empty in both (Quantity-left date
  arithmetic is not a defined operand order; only date ± quantity).
- `'2015-02'.toDateTime() + 4 days` → `2015-02` (§6.7 truncation to the date
  operand's precision — pinned doctrine).
- `'5'.toDecimal() < 6 '1'` → empty in both (Decimal↔Quantity ordering not
  defined, while equality `'5'.toDecimal() = 5 '1'` is true).
- Full-precision vs day-precision converted DateTime equality → empty
  (partial temporal precision doctrine).

## Validation

- Focused: `test_conversion_parity.py` 41/41 pass (incl. new regression).
- Full conformance gate: see architect handoff (run post-fix).
