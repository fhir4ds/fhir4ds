# QA Handoff — FP-18 EXPLORER (launch 3, iteration 1)

Personality: EXPLORER. Chunk: FHIRPath §6.6 Math + §6.7 Date/Time Arithmetic.

## What was probed
91-case dual-path probe (native extension vs forced Python fallback; core strict
engine for the two findings): `.temp/qa/fp18_explorer3_2026_08/probe.py`.
Spec text verified against FHIRPath N1 §6.6/§6.7 (fetched
spec/N1/index.adoc from github.com/HL7/FHIRPath) and official R4 fixtures
(testConcatenate1-4, testPlus/testMinus/testDiv/testMod families).

Angles covered (per EXPLORER brief):
- `&` chains with empty at depth, mixed implicit toString (int/decimal/bool/
  Quantity/date/Time/dateTime literals, kitchen-sink chain), multi-item &,
  error-operand & (`'a' & (1/0)`).
- Arithmetic feeding comparisons feeding boolean chains, `implies`, `iif`,
  div/mod-zero emptiness.
- div/mod sign matrix at negatives and exact multiples; Decimal divisors;
  Decimal div/mod by zero.
- Long arithmetic at int64 bounds (+1, *2, min-1, div 1, mod 1) and
  unary-minus chains incl. `- -LLONG_MIN`.
- Temporal month-end clamping (Jan31+1mo→Feb29, Feb29+1yr→Feb28, Mar31-1mo,
  Dec31+2mo), fractional-quantity truncation, invalid units ('mo', 'kg'),
  dateTime-dateTime and date-date subtraction, Time ± quantities at
  hour/minute/second/ms precisions incl. midnight wrap/underflow and
  hour-precision Time + minutes (correct no-op per §6.7 partial-precision rule).
- Arithmetic inside where/select/repeat with `$this`; unary minus chains
  (`- -5`, `- - -2.5`, `2 - -3`, `-(3+4)`, field negation).

## Verified CLEAN (both engines, matches spec/fixtures)
All of the above except the two findings below: month-end truncation matches
N1 §6.7 ISO8601 table exactly on both engines; Time arithmetic renders bare
(no leading T) with correct wrap; `&` empty semantics match
testConcatenate1-3; multi-item & and invalid units are execution-errors→empty;
div/mod truncation signs exact at int64; Long binary overflow degrades to
Decimal identically on both engines; dateTime−dateTime consistently empty on
both engines (no §6.7.2 operator defined in N1).

## Findings
- QA-001 MEDIUM CONFIRMED — unary-minus Long overflow parity: `- -9223372036854775808L`
  native→empty, fallback/core→raw Python int 2^63 (out-of-domain, renders without
  `.0`, unlike the documented overflow→Decimal doctrine the binary `+` path
  follows on BOTH engines, e.g. `9223372036854775807L + 1L`→`...808.0`).
- QA-002 MEDIUM CONFIRMED — `&` implicit conversion of complex JSON values:
  fallback emits Python dict repr (`{'value': 3, ...}`); native emits compact
  JSON serialization. Parity violation + non-canonical string form.
- QA-003 LOW INTENDED — unary-minus Integer overflow renders Long-style
  (`2147483648` no `.0`) vs binary Decimal degrade (`2147483648.0`);
  identical on both engines, unpinned by fixtures; documented, not fixed.

Handing off to Remediation.
