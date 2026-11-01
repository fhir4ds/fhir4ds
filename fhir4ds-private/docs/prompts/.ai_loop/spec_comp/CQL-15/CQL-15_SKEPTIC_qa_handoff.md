# QA Handoff — CQL-15 SKEPTIC (Interval operators Part 1)

## Verdict: CLEAN — ~30 fresh dual-path cases + adjudication micro-probes; 0 parity diffs; 0 defects

All initial flags adjudicated as probe-expectation errors with direct re-verification
(both engines identical on every row):

- **after/before STRICT semantics** (fixtures CqlIntervalOperatorsTest.xml :12-55):
  `A after B` = start(A) > end(B) (whole-interval; NOT end-vs-start);
  `A before B` = end(A) < start(B). [1,5] after [2,3] → False (1 not > 3);
  [6,9] after [1,3] → True; [2,5] before [1,3] → False.
- **ends direction**: LEFT operand ends within RIGHT (start(L)>=start(R) AND
  end(L)==end(R)): Interval[1,5] ends Interval[3,5] → False; [4,10] ends [1,10] → True
  (fixture IntegerIntervalEndsTrue analog).
- **collapse meets-successor-adjacency**: successor(3)=4 so {[1,3],[4,5]} MEET →
  merge to 1; gap {[1,3],[6,9]} → 2; overlap {[1,4],[3,6]} → 1.
- **except null-collapse**: proper-interval violations render [] at the population
  surface; disjoint except returns the left interval JSON.
- **interval rendering**: raw intervals render LIST-wrapped JSON strings
  ('{"low": "3", "high": "5", ...}'); Length(interval) = JSON-string char count
  (Length is String-only — R4 got 64 for the intersect JSON text).
- **expand renders**: JSON-STRING lists ('[1,2,3]'); per-hour T-forms short
  ('["T10","T11","T12"]'); half-open high excluded per fixtures.
- **includes month of cross-type**: Integer-interval includes temporal → False;
  precise temporal form → True.
- **grammar**: `size of (...)`/`count of (...)` parenthesized forms ParseError
  (use Length()/Count()).

Evidence: .temp/qa/speccomp2/cql15_skeptic_probe1.py (flagged=0 final) + /tmp/opencode/cql15_adj.py
