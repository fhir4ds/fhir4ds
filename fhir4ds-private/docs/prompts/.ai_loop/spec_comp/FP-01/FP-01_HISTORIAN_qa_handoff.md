# QA Handoff — spec_comp FP-01 (FHIRPath §4.1 Literals) — HISTORIAN

## Verdict: CLEAN — 0 issues logged
Systematic spec-walkthrough of the §4.1 normative literal grammar + narrative
range/shape rules. Dual-path (native vs forced fallback) parity held on every
case; spec-expected values verified. FRESH evidence only (45 new cases).

## Probe batteries (.temp/qa/speccomp2/fp01_historian_probe{,2}.py)
- probe1 (25 grammar-table cases): every §4.1 production walked — Boolean,
  String quoting+escapes, Integer range, Decimal precision, Date components,
  Time, DateTime+offsets, Quantity (UCUM quoted + calendar bare), documented
  equalities (1 year=12 month; 1 minute=60 seconds; 1 'min'=60 's'), toString
  examples. 4 flagged rows were probe-comparison artifacts (val_ok heuristic
  quote-stripping on list-wrapped JSON forms; direct re-check showed exact
  spec values on both engines).
- probe2 (20 shape/range cases): int32 out-of-range → empty; .5/5./1e3 not in
  grammar → empty; month 13/0, Feb 30, non-leap Feb 29 → empty (leap 2020
  valid); T24:00/T12:60 → empty; offset ±14:00 valid / +14:01 / −14:30 →
  empty; '4 Days' rejected (calendar keywords case-sensitive); '4 m' bare
  rejected. The one flagged row ('\u005' → 'u005' on BOTH) is the documented
  invalid-escape-takes-literal-chars rule (spec example TestEscape4) — probe
  expectation wrong, engines correct.
