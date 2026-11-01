# QA Handoff — CQL-15 EXPLORER (iteration 1, 2026-08-21)

Personality: EXPLORER. ~130 dual-engine probes (py fallback + native cpp) in
`.temp/qa/cql15_explorer3_2026_08_21/probe{1..5}.py`, verified against the
cached CQL 1.5 §9 reference text (`.temp/qa/cql15_skeptic/cqlref.txt`) and the
HL7 DBCG Java reference engine `ExpandEvaluator.java` (fetched to /tmp).

## Probed (all clean unless listed below)
- After/Before boundary contact with all open/closed combinations incl.
  point-adjacency [1,1] after [1,1] (false), open-low/open-high touching
  (strict semantics honored) — conformant on both engines.
- Contains/In at exact boundary points with open vs closed bounds and
  precision truncation — conformant.
- Starts/Ends with degenerate single-point intervals (incl. precision) —
  conformant for literal operands.
- Except partial-overlap, nested, point-hole, adjacent, disjoint, identical,
  list-of-intervals — conformant for literal/list operands.
- Expand grids: day/month/year around month boundaries (leap day incl.),
  Quantity intervals with unit conversion (50 'cm' grid over 'm' interval),
  default per, open high bound — conformant.
- Equal/Equivalent open-vs-closed bounds, degenerate, null bounds — conformant.

## Issues opened

### QA-001 (HIGH, OPEN) — LIST_EXTRACT interval operands break §9 routing
`First({Interval[...]})`, `Last(...)`, `collapse(...)[i]` lower to
`LIST_EXTRACT(...)` which `_is_fhir_interval_expression`
(fhir4ds/cql/translator/expressions/_temporal_intervals.py:465) does not
recognize. Consequences (py and cpp agree in being wrong):
- `... contains 5` / `5 in First(...)` → DuckDB string-contains Binder Error.
- `First(...) after/before Interval[...]` → UDF TypeError (int/str compare).
- `First({Interval[4,6]}) ends Interval[1,6]` → **silently false** (should be
  true): the `{low,high}` bounds-list coercion re-wraps LIST_EXTRACT as
  `intervalFromBounds(x, x)`. Same for `starts`.
- `(collapse ... per 2)[1] except Interval[4,6]` → null instead of the interval
  pieces.
- `expand First({Interval[4,6]}) per 1` → list of degenerate interval structs
  instead of points `[4,5,6]`.

### QA-002 (MEDIUM, OPEN) — Expand per-precision boundary truncation (temporal)
Spec §9 Expand: boundaries more precise than per are truncated to per
precision; boundaries less precise (temporal uncertainty) contribute nothing.
Actual: `expand Interval[@2024-01-01T10:30, @2024-01-01T12:00] per hour` →
`{T10, T11}` (missing T12); `expand Interval[@2024-01, @2024-01] per day` →
`{2024-01-01}` (should be {}). Numeric low truncation (prose) is NOT performed
by the DBCG reference engine either (grid starts at interval start); our
numeric behavior matches the reference engine — prose-vs-reference divergence,
do not "fix" numeric without reference backing.

## Notes for Remediation
- QA-001 fix should extend `_is_fhir_interval_expression` to recognize
  LIST_EXTRACT/list_extract whose first arg is interval-producing (list of
  intervalFromBounds, collapse_intervals output, etc.), and ensure the
  bounds-list coercion path does not fire for such expressions. This is the
  same bug family as the CQL-15 HISTORIAN CMS128 recovery (missing UDF/name
  recognition sites) — grep ALL recognition sites after adding.
- Watch DQM/CMS128: interval recognition changes are DQM-sensitive.
