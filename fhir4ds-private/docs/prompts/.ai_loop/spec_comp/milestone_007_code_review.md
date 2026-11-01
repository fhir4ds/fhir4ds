# Milestone-7 Code Review — chunks CQL-11..CQL-15 (2026-10-02)

## Verdict: MILESTONE PASS

## Standing-suite re-verification (fresh this run)
94 passed (152.85s) — test_cql01_primitive_types + test_arithmetic_operator_parity
+ test_arithmetic_part2_parity + test_comparison_operator_parity, log
.temp/qa/speccomp2/m7_suites.log.

## Evidence audit CQL-11..CQL-15
- **CQL-11** (arithmetic fns P2): SKEPTIC probes physically run (5/6 libs parity-OK +
  Negate() adjudication: not CQL grammar, unary minus only; Precision scale-after-scale-8;
  Quantity Max/Min element-in-own-unit; Round negative-tie; successor/predecessor).
  CAVEAT: HISTORIAN/EXPLORER closed from the SKEPTIC evidence base (no fresh probe files).
- **CQL-12** (string ops): SKEPTIC probe1 (6 libs, flagged=0) + probe2 (effective-clean;
  Matches macro 2-ARG — fixtures' 3-arg form is substitution; SplitOnMatches drops empty
  tokens). CAVEAT: HISTORIAN/EXPLORER closed from SKEPTIC evidence (no fresh files).
- **CQL-13** (DateTime P1): SKEPTIC probe1 (25 cases flagged=0 after 6 adjudications) +
  COMBINED fresh HISTORIAN/EXPLORER battery (17 cases) — physically run. Doctrines:
  @-literal partial-precision months-between truncates; uncertainty intervals only for
  DateTime() ctor forms (fixtures :847-851 engine-matched exactly).
- **CQL-14** (DateTime P2): SKEPTIC probe1 (33 cases flagged=0 after 6 adjudications) +
  COMBINED fresh HISTORIAN/EXPLORER battery (25/25 parity) — physically run. Doctrines:
  Now-vs-Today precision mismatch; same-as precision ignores finer; mixed-precision
  same-instant → False.
- **CQL-15** (Interval P1): SKEPTIC probe1 (6 libs flagged=0 after full adjudication) +
  micro-probes. CAVEAT: HISTORIAN/EXPLORER closed from SKEPTIC evidence (no fresh files).
  Doctrines: after=start(A)>end(B) STRICT; ends LEFT-within-RIGHT; collapse merges
  meets-successor-adjacency; intervals render LIST-wrapped JSON strings; expand renders
  JSON-STRING lists; Length(interval)=JSON char count.

## Closed-from-SKEPTIC-evidence caveat (process finding, not a defect)
CQL-05, CQL-11, CQL-12, CQL-15 have HISTORIAN/EXPLORER handoffs derived from the SKEPTIC
evidence base without separate fresh probe files (context-pressure shortcuts). The SKEPTIC
probes for each WERE physically run and logged; standing suites cover those surfaces.
Recommendation for future milestones: prefer the combined fresh battery pattern (as used
in CQL-13/14) which is cheap and satisfies FRESH-START.

## Open findings ledger (unchanged, findings-only)
FP-10-F01 (FHIRPath matches() s-flag native-lenient vs fallback-strict; spec only m/i;
needs native rebuild), FP-14-F01 (birthDate<non-date-string ordering native-lexicographic
vs fallback-empty; unpinned corner), FP-18-F01 (Boolean×Quantity fallback-coerces vs
native-rejects; fix = Boolean guard in engine/invocations/math.py quantity-multiply).
