# Engineer Handoff — CQL-14 iteration 1 (EXPLORER), fixes for QA-001/QA-002

## Triage
| Issue | Category | Severity | Disposition |
|---|---|---|---|
| QA-001 starts/ends `same <prec> or after/before` qualifier dropped | SPEC_VIOLATION | HIGH | RESOLVED |
| QA-002 starts/ends `on or before/after <prec> of` ignores precision | SPEC_VIOLATION | HIGH | RESOLVED |

## QA-001 (HIGH) — CQL 1.5 grammar `'same' dateTimePrecision? (relativeQualifier|'as')` (§9.18/§9.19/§9.25/§9.26)
- Root cause (two layers):
  1. Parser (fhir4ds/cql/parser/parser.py, starts/ends `same` branches):
     after the optional precision token the code did an unconditional
     `advance()` assuming `as`; for `starts same day or after X` it consumed
     the OR_AFTER token and emitted operator `starts same day as` → same-as
     equality. No-precision `starts same or after X` failed the lookahead
     gate entirely → ParseError.
  2. Translator (_operators.py `_translate_tail_operators`): any operator
     matching `starts ... ' or ' ...` was routed into
     `_translate_complex_interval_temporal` (quantity-offset semantics)
     before the `starts same ` delegation could run.
- Fix: parser now matches `same [prec] (as | or after | or before)` and emits
  `starts/ends same[ prec] or after|or before`; the complex-quantity branch
  excludes the `same` family. Existing `_translate_same_operator` patterns
  (`same {prec} or after/before`, `same or after/before`) then lower to
  cqlSameOrAfterP/cqlSameOrBeforeP (precision) and cqlSameOrAfter/
  cqlSameOrBefore (no precision), with intervalStart/intervalEnd bound
  extraction per §9.25/§9.26 — matching the reference cql-to-elm
  `visitConcurrentWithIntervalOperatorPhrase` (SameOrAfter(Start(A), B)).
- Single fix serves both engines (shared SQL; no C++ changes).

## QA-002 (HIGH) — CQL 1.5 §9.18/§9.19/§9.25/§9.26: comparisons at the specified precision on BOTH bounds
- Root cause: `starts/ends on or before|after <prec> of X` parses as
  starts/ends wrapping `UnaryExpression('on or before', precision-of X)`;
  `_translate_starts_op`/`_translate_ends_op` hardcoded DATE casts on both
  sides for the simple inner on-or forms, silently forcing day precision on
  the interval-bound side while the inner `precision of` truncated only the
  right operand → false negatives at year/month (day-collapse at finer).
- Fix: both functions detect an inner `precision of` operand and lower to
  cqlSameOrBeforeP/cqlSameOrAfterP with intervalStart/intervalEnd at the
  specified precision (mirroring the existing unqualified
  `_prec_temporal_match` path); FHIR-interval right operands still resolve
  to start/end bounds. Non-precision forms keep the prior DATE path.

## Regression coverage
New dual-engine test:
`fhir4ds/cql/duckdb/tests/integration/test_datetime_part2_parity.py::
test_cql_datetime_part2_starts_ends_same_or_and_on_or_precision`
(18 assertions across Python + native engines, including negative cases,
hour precision, no-precision forms, interval right operands per §9.25/§9.26,
and the §9.24 singleton-semantics non-regression `starts same day as
Interval[...]` → false).

## Validation (fresh, this launch)
- test_datetime_part2_parity.py: 9/9 passed.
- Focused temporal/interval parity suites (part1+temporal_complex+interval
  1-3): 79 passed / 0 failed.
- Related unit filter (temporal/time/interval/same/parser): 223 passed.
- Master conformance gate: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47) — baseline held.

No workarounds; no SQLRaw/silent-fallback violations; no C++ edits
(single-writer discipline respected; dual-engine parity by construction).
