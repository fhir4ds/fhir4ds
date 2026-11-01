# QA Handoff — FP-11 §5.7 Math (EXPLORER), iteration 1

Personality EXPLORER: boundary/extreme/combination probing on code as left by
SKEPTIC + HISTORIAN fixes. Probe: /mnt/d/fhir4ds/.temp/qa/fp11_explorer/
(probe.py, probe2.py), dual-path native vs forced Python fallback,
PYTHONPATH=/mnt/d/fhir4ds. Spec verified against FHIRPath R4/N1 §5.7 + §5.5.8
toString (cached spec text quoted in evaluator.cpp doctrine comments).

~90 fresh cases: power towers (2.power(10).power(10), 3.power(3).power(3)),
extreme magnitudes (10.power(±300), 2.0.power(1024/-1023), (0.5).power(1074/1075)),
denormal ln ((0.5.power(1074)).ln()), 1.0000001.power(1000000) e-approximation
boundaries, sqrt of exact/tiny squares (1e-27, 1e-28, 1+4e-28), round with
precision extremes (20, -20 -> error, 2.5 -> error, 0/-2 negative-precision
ties 150/250/350 -> error per STU3 non-negative), truncate/floor/ceiling at
exact integer boundaries, on -0.0, on 28-digit near-1 decimals, abs of int32
min and -2^63 (empty, both), math inside iteration contexts (select/where over
nums, multi.select(v.power(2))), results feeding =/> comparisons and
cross-function identities (sqrt vs power(0.5)).

Clean on both engines: all of the above except two native defects:

QA-001 HIGH — native `formatDecimalNumber` renders non-integer values < 1 via
`std::fixed << setprecision(15)`, truncating significant digits behind leading
fractional zeros: `0.000000000000001.sqrt()` -> '0.000000031622777' (fallback
'0.00000003162277660168379'), `0.000000000000000000000000001.sqrt()` ->
'0.000000000000032' (~1% error), `1e-28.sqrt()` -> '0.0'. Large values render
the exact binary64 expansion while the fallback renders the
Decimal(str(float)) shortest expansion ((2.0.power(1023)).sqrt() diff).
fhirpath_number parity is intact (decimal_val correct); corruption is on the
toString surface.

QA-002 MEDIUM — native exact-power caps (scale>20, >10000 magnitude digits,
negative-exp total_scale>100) silently degrade to std::pow while the fallback
computes Decimal 28-sig: `1.0000001.power(1000000)` -> 1.1051709126143208
(wrong at the 11th significant digit; true/Decimal 1.105170912549793416638382709);
`0.000000000000000000000000001.power(2)` -> '0.0' vs exact 1e-54.

Non-issues re-confirmed: scientific-notation literals (1e300) are not FHIRPath
number literals (syntax error, both engines); negative/fractional round
precision errors identically; power-of-power Integer typing stable; all four
SKEPTIC fixes + HISTORIAN helper fixes intact on fresh variants.
