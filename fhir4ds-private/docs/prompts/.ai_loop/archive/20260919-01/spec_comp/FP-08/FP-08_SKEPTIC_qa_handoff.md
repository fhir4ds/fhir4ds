# QA Handoff — FP-08 SKEPTIC (iteration 1, 2026-08-17)

Chunk: FHIRPath §5.5.7 toQuantity/convertsToQuantity, §5.5.8 toString/convertsToString, §5.5.9 toTime/convertsToTime.

## Method
87 + 50 fresh dual-path probe cases (native C++ extension vs Python fallback)
run with PYTHONPATH=/mnt/d/fhir4ds; spec table verified against
hl7.org/fhirpath §5.5.7 normative conversion-factor table; official R4
fixture expectations cross-checked (tests-fhir-r4.xml lines 239-439, 659-663).

## Verified clean (no issue)
- toString rendering of every literal type: boolean, integer, negative
  integer, decimal precision/trailing zeros (1.50 → "1.50"), date/year-month/
  year, dateTime, Time (T-less canonical), Quantity UCUM ("1 'wk'") and
  calendar keyword ("4 days"), string identity (no quoting).
- convertsToString for all literal types; empty input → empty; multi-item
  → error/empty doctrine in both paths.
- toTime grammar: bare and T-prefixed full/partial times, millisecond
  fractions, invalid hour/minute rejection, timezone-bearing strings
  rejected, non-string/non-grammar inputs rejected, Time passthrough.
- toQuantity: Integer/Decimal/String/Boolean → '1' conversions (incl. value
  text precision '0.0' → "0.0 '1'"), UCUM quoted strings, bare calendar
  keywords, case-sensitivity, within-group conversions (year↔month=12,
  wk↔d=7, d↔h=24, h↔min=60, min↔s=60, kg↔g=1000, cm↔m=0.01),
  calendar↔UCUM same-category (year↔'a', month↔'mo', second↔'s'),
  incompatible-dimension rejection.

## Issues found
- QA-001 (MEDIUM, SPEC_VIOLATION §5.5.7): the spec's canonical conversion
  table rows "1 year = 12 months or 365 days" and "1 month = 30 days" are
  not honored by toQuantity's unit argument: (1 year).toQuantity('day'),
  (1 month).toQuantity('day'), (1 day).toQuantity('month'),
  (2 months).toQuantity('days'), (1 year).toQuantity('week') all return
  empty in BOTH engines. Root cause: the calendar-vs-UCUM group separation
  landed for §6.1 equality semantics (June FP-08 EXPLORER) also blocks
  calendar-keyword ↔ calendar-keyword conversions, which the §5.5.7 table
  explicitly defines. Equality grouping (12×30=360≠365) must stay separate;
  only the toQuantity/convertsToQuantity path should bridge using the
  direct table factors (year↔month 12, year↔day 365, month↔day 30;
  sub-day units via seconds).
- QA-002 (MEDIUM, PARITY/§4.1.4): non-terminating duration conversions
  diverge between engines: (1 's').toQuantity('min') native
  "0.0166666666666667 'min'" (15 sig digits, double shortest-round-trip
  cap) vs fallback "0.01666666666666666666666666667 'min'" (28 sig digits,
  Decimal). Same for (1 month).toQuantity('year'), (1 day).toQuantity('week').
  FHIRPath Decimal semantics (§4.1.4, .NET decimal lineage) require 28
  significant digits; the native conversion path computes in binary64 and
  caps rendering at 15 sig figs (deliberate June mask).
- QA-003 (HIGH, PARITY bug in fallback): 'T14:34'.toTime() = @T14:34 →
  false in the Python fallback, true in native. FP_Time.__init__ strptime
  format list lacks non-timezone "T%H:%M" and "T%H" forms, so T-prefixed
  partial times get no _pyTimeObject; FP_TimeBase.equals then compares
  _getDateTimeInt() None vs 52440 → false. Seconds-precision T-forms work
  ("T%H:%M:%S" is present), which is why only hour/hour:minute break.

## Reproducers
.temp/qa/test_fp08_skeptic.py, .temp/qa/test_fp08_round2.py
