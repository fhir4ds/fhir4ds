# QA Handoff — FP-13 launch, iteration 1 (SKEPTIC)

Chunk: FHIRPath §6.1 Equality — =, !=, ~, !~ (Quantity, Date/Time, String, Decimal, collections).

## What was probed
- Dual-engine battery (.temp/qa/fp13_probe{,2,3}.py): 100+ cases across native
  fhirpath UDF and forced Python fallback, all four operators.
- Doctrine re-verification (FP-01..FP-13 pins): mixed calendar/UCUM year-month
  equality EMPTY + equivalence TRUE; offset-temperature EMPTY; union dedup;
  Time-vs-String empty; fixture collection semantics. All pins HOLD.
- Fresh ~ semantics: string whitespace (per-char normalization, no collapsing),
  case folding, decimal trailing-zero/least-precision rounding, temporal
  reduced-precision false-vs-empty (incl. Date vs DateTime -> false), quantity
  tolerance edges, year/month conversion equivalence, 23 ~ 23 '1', empty
  propagation for ~/!~/=/!=, incompatible types (~ -> false, = -> empty),
  multi-item order-independent equivalence, !=/!~ exact negation on empty.

## Findings
- QA-001 (HIGH, OPEN): native decimal `~` uses the MOST precise operand's
  scale when the other operand is integral (`cmp_prec` max fallback), violating
  §6.1.2 least-precision rounding and diverging from the Python fallback.
  `1.0 ~ 1.0001` native=false fallback=true; also `1 ~ 1.4`, `0 ~ 0.4`,
  `1.0 ~ 1.06`. Sites: evaluator.cpp valuesEquivalentState (source_text and
  double paths) + jsonNumbersEquivalent.
- QA-002 (LOW, INTENDED): `23 'Cel' ~ 73.4 '[degF]'` EMPTY vs N1 example
  true — pre-pinned affine-conversion doctrine, re-verified.

Everything else clean, including all official R4 fixture semantics
(testEquivalent*/testNotEquivalent*/testNEquality* families).
