# Engineer Handoff — FP-01 EXPLORER Iteration 1 FIX (2026-08-16)

## Scope
2 issues: QA-001 (HIGH, native binary64 Decimal arithmetic corruption),
QA-002 (HIGH, division not Decimal in both engines). Both RESOLVED.

## Triage table
| ID | Sev | Category | Terminal | One-line outcome |
|---|---|---|---|---|
| QA-001 | HIGH | PARITY_DIVERGENCE | RESOLVED | Native `+ - *` (and `/`, see QA-002) over exact-digit operands now uses exact Decimal string arithmetic mirroring the Python fallback's `decimal` module (28 sig digits, ROUND_HALF_EVEN); identity ops no longer corrupt >16-sig-digit decimals. |
| QA-002 | HIGH | SPEC_VIOLATION §6.6.2 | RESOLVED | Fallback `math.div` converts Integer operands to Decimal (division is always Decimal) + InvalidOperation guard on the integral quantize (pre-existing UDF crash); native division uses exact long division with guard-digit streaming, tie-break continuation, and the fallback's integral one-decimal quantize. |

## Design decision (spec-grounded)
No official R4 fixture pins raw division display/equality (only
`(1.2/1.8).round(2)` at tests-fhir-r4.xml:907-908; `iif(true,true,1/0)`
lazy; Quantity division tests go through the Quantity branch), so §6.6.2
("The result of a division is always Decimal, even if the inputs are both
Integer") + the project's native/fallback byte-identical-output invariant
govern. The Python core engine runs R4 conformance (935/935), so its
Decimal semantics are canonical; the native path was brought to it.

## Implementation
Native (`extensions/fhirpath/src/fhirpath/evaluator.cpp`):
- New exact Decimal string arithmetic after `tryIntegerArithmeticText`:
  `FpDecimalDigits` (sign/digits/exponent), `parseFpDecimalDigits`
  (Integer, JSON int, or plain source_text only — JSON reals and text-less
  Decimals defer to the binary64 path), `roundFpDecimalTo28`
  (ROUND_HALF_EVEN, carry-aware), `fpDecAddSub` (min-exponent alignment,
  IBM zero-sign rules: left sign for both-zero adds, positive zero for
  nonzero cancellation), `fpDecMul` (ideal exponent, XOR sign incl. zero),
  `fpDecDiv` (schoolbook long division; streams to 29 significant digits
  with a tie-break continuation loop — a non-exact quotient ALWAYS produces
  a nonzero digit after a '5' guard within ~log10(divisor) digits, else the
  division would terminate exactly; 512-cap paranoia), and
  `fpDecToPlainText` (`format(d,"f")` semantics; zero keeps its
  ideal-exponent scale: `0 * 0.0000001` → `0.0000000`).
- `tryDecimalArithmeticText` wrapper adds the fallback's division-integral
  quantize to one decimal place (guarded by the 28-digit coefficient cap,
  mirroring the Python quantize-guard), superseding the FP-14
  integer-valued-only gate in `evalBinaryOp`; `+ - *` keep the
  Integer+Integer fast path per §4.1.3; `/` always routes through when
  exact digits exist; zero-divisor check hoisted (12/0 → empty).
- `decimal_val` re-anchored via `strtod(source_text)` (FP-11 pattern) so
  `fhirpath_number` equals `float(Decimal)`.
- Stale FP-18 HISTORIAN comment (float-truediv assumption) corrected.
- Rebuilt twice + deployed the bundled
  `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

Python (`fhir4ds/fhirpath/engine/invocations/math.py::div`):
- Integer operands converted to Decimal before `x / y` (§6.6.2), fixing
  `1 / 3 = 0.3333333333333333` evaluating false while displaying that text.
- Integral `quantize(Decimal("0.1"))` wrapped in try/except
  InvalidOperation: ≥28-digit quotients (e.g.
  `9999999999999999999999999999.99999999 / 1`) previously crashed the whole
  DuckDB UDF (pre-existing latent bug exposed by the differential corpus).

Tests (`fhir4ds/fhirpath/duckdb/tests/integration/test_arithmetic_parity.py`):
- NEW `test_decimal_arithmetic_exact_text_parity_fp01_explorer` (14 cases:
  identity ops, binary64 noise, cancellation, 28-digit rounding contexts,
  signed zero, zero-scale products).
- NEW `test_division_decimal_equality_semantics_parity_fp01_explorer`
  (10 boolean cases incl. the exact QA evidence).
- NEW `test_division_no_scientific_notation_in_json_fp01_explorer` (4 JSON
  transport cases).
- UPDATED `test_division_uses_shortest_roundtrip_text_fp18_historian`
  expectations (7 old + 6 new cases) with the §6.6.2 rationale — the old
  expectations encoded the float-truediv violation.

## Mid-fix defects found and fixed during development
Corpus iterations exposed three bugs in the first implementation (guard
digit missing → ties rounded down; zero-scale rendering; missing
integral-quantize parity) plus the validator's int/int modeling error and
one invalid-literal test case (`12345678901234567` bare is invalid in both
engines — >int32 without a decimal point). All resolved; final corpus 0 FAIL.

## Validation (PROC_VALIDATION Recovery Gate)
- Differential corpus (native text vs Python Decimal ground truth,
  46 operands × 4 ops + signed-zero/chained extras): **8463 computed,
  0 FAIL** (`.temp/qa/fp01_explorer_2026_08_16/difftest.py`).
- EXPLORER probes 1-5 on final state: **0 parity divergences** (incl.
  probe3 28 division cases and probe4 22 precision cases that found the
  bug).
- Extra surface check: `fhirpath_number`, `.toString()` parity on division
  results OK (re-anchor verified).
- Focused parity files: **187/187**.
- Full fhirpath package pytest: **1608 passed, 0 failed**.
- CQL package pytest: **5631 passed, 9 skipped (env), 0 failed**.
- FINAL full conformance `run_all.py`: **2832/2832** (ViewDefinition
  144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47) — baseline held.
  Summary: `.temp/qa/fp01_explorer_2026_08_16/conformance_summary.log`.

## Notes for Architect
- The fix deliberately leaves `div`/`mod` on the legacy trunc paths
  (unchanged semantics; not part of either issue).
- JSON reals without source text still take the binary64 path in native —
  identical to pre-fix behavior for data-sourced values; literal and
  chained-arithmetic flows (the QA evidence) are exact.
- The Python `div` InvalidOperation guard fixed a pre-existing crash class
  that QA had not directly logged (huge integral quotients); folded into
  QA-002's remediation since it is the same code site.
