# Engineer Handoff — FP-13 launch, iteration 1

## QA-001 (HIGH, RESOLVED): native decimal `~` least-precision violation
- Root cause: four native sites computed the comparison precision as
  `min` only when both operands had >0 decimal places, else `max` — so an
  integral operand (precision 0 after trailing-zero strip) let the MORE
  precise operand govern (`1.0 ~ 1.0001` → false; `1 ~ 1.4` → false),
  violating §6.1.2 ("rounded to the precision of the least precise
  operand") and diverging from the Python fallback (`is_equivalent`).
- Fix: `cmp_prec = min(l_prec, r_prec)` everywhere, with rounding applied
  at precision 0 as well:
  1. evalBinaryOp singleton source_text path
  2. evalBinaryOp singleton double fallback (now via
     decimalPlacesFromNumberText, which strips trailing zeros)
  3. valuesEquivalentState lambda (multi-item `~`)
  4. jsonNumbersEquivalent (JSON numeric operands)
- File changed: extensions/fhirpath/src/fhirpath/evaluator.cpp
- Extension rebuilt (make fhirpath_loadable_extension) and redeployed to
  repo bundle fhir4ds/fhirpath/duckdb/extensions/, /tmp/duckdb_cpp_ext/,
  and user site-packages.
- Regression test: test_decimal_equivalence_least_precision_parity_fp13_skeptic
  (fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py,
  14 parametrized cases across native + forced fallback).
- Validation: focused parity suite 40/40 passed; full conformance
  2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47) — baseline held.

## QA-002 (LOW, INTENDED): offset-temperature equivalence
No change; prior FP-13 HISTORIAN pin re-verified holding in both engines.
