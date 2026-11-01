# QA Handoff — CQL-21 EXPLORER iteration 1

Personality: EXPLORER (fuzz/combination probing). All probes run with
PYTHONPATH=/mnt/d/fhir4ds on BOTH the Python-fallback engine and the native
C++ engine (md5 da6c07adb08ef224d0621b9d222b6bae, matched repo+site-packages);
py and cpp agreed on every result below (no parity failures).

## Probes (workspace .temp/qa/cql21_explorer/)
- Timezone-offset birthDates (`2000-05-14T23:30:00-05:00`) → time+offset
  dropped, day-precision uncertainty interval emitted ({16200..102600} s).
  FHIR birthDate is a `date`; a timestamp is invalid FHIR, so treating it as a
  day-precision date is defensible — NOT a bug.
- Offset asOf (`@2000-05-15T00:00:00-05:00` vs Z) over day-precision births:
  both {0,1} days — correct day uncertainty either way.
- Exact-anniversary crispness: 2000-05-14 @ 2026-05-14 → crisp '26' ✓;
  leap-day 2000-02-29 → 26 ✓.
- Leap-day Months/Days/Weeks (2020-02-29 @ 2021-02-28): 12 / 365 / 52 ✓.
- Year-precision birth ('1990') at all precisions → proper §22.21 intervals;
  `in Interval[18,65]` and boundary `in Interval[35,36]` → True via
  cqlUncertainCompare (SKEPTIC fix holds).
- In(ValueSet) declared-but-unloaded: direct UDF NULL + warning ✓;
  population column False (documented define-boundary collapse).
- ExpandValueSet on declared-but-unloaded set: null; Count(...) null ✓.
- Concept Equivalent overlap (BP ~ BPSwap, non-empty intersection) → True ✓;
  Concept Equal disjoint → False ✓.
- Sum/Median over lists mixing crisp and interval ages.
- Retrieved-vs-literal Code Equal/Equivalent with matched display.

## Issues opened
- QA-001 HIGH OPEN — Equal (=) on dynamically retrieved code vs literal Code
  is ALWAYS False (no dynamic lowering path; raw CodeableConcept-JSON vs
  Code-JSON comparison). `~` has the dynamic path and returns True on
  identical operands. Spec: = on codes matches code+system+version+display;
  matched-display case must be True. Silent wrong boolean.
- QA-002 MEDIUM OPEN — Sum/Median over a list containing an uncertainty
  interval age silently drop the uncertain element (crisp 26 instead of
  {61,62} or null). Same family as HISTORIAN QA-002 (Min/Max only).
- QA-003 MEDIUM OPEN — Average() translates to unregistered SQL `Average`;
  DuckDB Catalog Error at execution (`Average({1,2,3})` crashes; no clean
  TranslationError).
- QA-004 LOW INTENDED — population-mode null→False collapse for unloaded
  valueset defines; documented filter-based behavior (direct UDF is NULL ✓).

## Not bugs (registry candidates)
- Timestamped birthDate treated as day-precision (FHIR date type).
- Sum returns Decimal surface (52.00000000) — cosmetic, value-correct.
