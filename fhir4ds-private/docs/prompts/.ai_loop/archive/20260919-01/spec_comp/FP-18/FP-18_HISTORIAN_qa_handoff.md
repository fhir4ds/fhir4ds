# QA Handoff — FP-18 HISTORIAN iteration 1 (2026-08-18)

Chunk: FHIRPath §6.6 Math Operations + §6.7 Date/Time Arithmetic (post-SKEPTIC-fix re-audit + fresh divergence hunt).

## Method
Three-engine probe matrix (native C++ extension, forced Python fallback UDF, Python core
`evaluate()`), spec text taken directly from hl7.org/fhirpath/N1 (v2.0.0) §6.6/§6.7,
fixture XML grepped (no official fixtures pin §6.7 arithmetic outputs or Quantity math
examples). Probes: `.temp/qa/fp18_historian2_2026_08/probe.py` (65 cases) and `drill.py`
(30 cases).

## Re-verification of SKEPTIC's 5 fixes — ALL INTACT
- Exact int64 div/mod: `9223372036854775807L div 1`, `2305843009213693951L mod 7` correct
  on all engines; native Integer div renders plain integers.
- Decimal mod exactness (28-digit) parity OK.
- Unsuffixed >INT32 unsuffixed literal errors (but see QA-006 edge: INT32_MIN).
- Quantity div/mod rejection and invalid §6.7.1 unit errors ('a'/'mo', Date+hours,
  Time+days) reproduce as fixed.
- div/mod fixtures (5.5 div 0.7 = 7 etc.), `&` empty-string semantics, `@2016 + 365 days`
  → 2017, `@2014 + 23 months` → 2015, month/year clamping — all correct on all engines.

## NEW findings (6 issues, all logged in evolution.json)
- QA-001 MEDIUM: native Quantity math normalizes to SI base units instead of the
  §6.6 normative most-granular-unit result (`3 'm' + 3 'cm'` → `3.03 'm'` vs spec `303 'cm'`;
  `12 'cm' * 3 'cm'` → `0.0036 'm2'`; `3 'cm' * 12 'cm2'` → non-canonical `0.000036 'm.m2'`).
  Fallback matches spec examples → native-only divergence + parity break.
- QA-002 MEDIUM: native §6.7 Time arithmetic results render with leading `T`
  (`T10:31:00`) while Time literals/`toString()` render without `T` on BOTH engines
  (§5.5.8 table: `hh:mm:ss.fff`). Native self-inconsistent + parity break with fallback.
- QA-003 MEDIUM: Integer arithmetic overflow silently promotes to Decimal on both engines
  (`2147483647 + 1` → `2147483648.0`); §6.6 preamble requires empty. `-2147483648 - 1`
  additionally parity-diverges.
- QA-004 MEDIUM: definite-duration UCUM units above seconds ('wk','d','h','min') are
  ACCEPTED in dateTime/Date/Time arithmetic by both engines; §6.7 requires an error.
  (SKEPTIC's fix covered 'a'/'mo' only.)
- QA-005 MEDIUM: fractional seconds dropped at second precision on both engines
  (`+ 1.5 seconds`, `+ 1500 'ms'` → whole second); §6.7 ignores the decimal portion only
  ABOVE seconds.
- QA-006 LOW: `-2147483648` (Integer minimum) rejected by core/fallback ("Integer literal
  out of range", range check applied pre-negation), accepted by native — parity edge.

## Verified clean (fresh angles, no issue)
Precedence `2+3*4`/`2 * -3`/`2 + -3`; `0.1+0.2`→0.3 and `1.1*1.1`→1.21 exact Decimal;
`4/2`=2.0 numeric; `7 div 2.0`=3; string `+` concat and `'a' + {}` empty; multi-item
operands error; year out-of-range (@9999+1 year, @0001-1 year) errors; `12 'cm' / 3`
= 4.0 'cm'; `5.5 mod 2`=1.5; `1000000*1000000*1000000` (see QA-003); mixed Integer/Decimal
implicit conversion results render Decimal (15.0, 9.5, 10.0).
