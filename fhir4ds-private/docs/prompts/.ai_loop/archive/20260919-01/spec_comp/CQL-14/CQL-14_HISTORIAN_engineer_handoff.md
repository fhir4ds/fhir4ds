# Engineer Handoff — CQL-14 iteration 1 (HISTORIAN), fixes for QA-001/QA-002

## Triage
| Issue | Category | Severity | Disposition |
|---|---|---|---|
| QA-001 no-precision interval same-or-after/before | SPEC_VIOLATION | HIGH | RESOLVED |
| QA-002 Time(null) translation crash | SPEC_VIOLATION | LOW | RESOLVED |

## QA-001 (HIGH) — CQL 1.5 §9.25 Same Or After / §9.26 Same Or Before
- Root cause: `_translate_same_operator` (fhir4ds/cql/translator/expressions/
  _temporal_comparisons.py) no-precision branches emitted
  `cqlSameOrAfter(intervalString, intervalString)`. The native UDF's
  `ExtractTemporalOperand` substitutes interval **low** for BOTH operands,
  yielding start-vs-start comparisons: `Interval[@2012-01-01, @2012-01-02]
  same or after Interval[@2012-01-01, @2012-01-03]` → native **true** (spec:
  false — start 01-01 is NOT on-or-after end 01-03). Python fallback cannot
  parse interval JSON → null. Precision variants were already correct because
  they extract bounds in SQL.
- Fix: no-precision branches now extract `intervalStart(left)`/`intervalEnd(
  right)` (same-or-after) and `intervalEnd(left)`/`intervalStart(right)`
  (same-or-before), points pass through unchanged — mirroring the precision
  branches and the spec's normative wording. One fix serves both engines;
  no C++ change required (the UDF no longer receives interval strings from
  the translator).
- Note: native `ExtractTemporalOperand` low-of-both behavior remains for any
  direct-SQL caller; it is no longer reachable from CQL. Flagged as an
  architectural note, not fixed (would require extension rebuild for a dead
  path).

## QA-002 (LOW) — CQL 1.5 §8.16 Time constructor
- Root cause: `_translate_time_pre` (_temporal_components.py) rejected any
  single non-int Literal — including `null` — with ValueError, while the
  multi-arg path handles static nulls (Time(null,null) → null).
- Fix: a null Literal routes to `_time_component_constructor`, yielding null
  (spec: "At least one component must be specified"; spec's own TimeInvalid
  example evaluates to null). Non-Integer literals (e.g. Time(1.5)) still
  raise — that is a genuine type violation.

## Regression coverage
New dual-engine test:
`test_datetime_part1_parity.py::test_cql_datetime_part2_no_precision_interval_same_or_and_time_null_ctor`
(13 assertions across both engines, incl. uncertainty case and point-only
non-regression).

## Validation (fresh, this launch)
- Focused parity suite: 21/21 passed.
- Temporal integration suites (-k temporal/datetime/interval): 95 passed /
  5 skipped / 0 failed.
- fhir4ds/cql/tests: 4916 passed / 4 skipped / 0 failed.
- Master conformance gate: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47) — baseline held.

No workarounds; no CQL GLOBAL_RULES violations (no SQLRaw, no silent
fallbacks); no C++ edits (single-writer discipline respected).
