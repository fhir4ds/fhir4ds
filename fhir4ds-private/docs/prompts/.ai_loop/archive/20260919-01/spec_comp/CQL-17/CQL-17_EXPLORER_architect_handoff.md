# Architect Handoff — CQL-17 EXPLORER (3rd launch, 2026-08-22)

## Scope
Focused architectural audit of this launch's diff (translator arithmetic
dispatch gate) against the CQL translator invariants in AGENTS.md /
GLOBAL_RULES.md, plus the QA-enforcer gate.

## Audit of the fix (QA-001)
- Layering: the gate lives entirely in the translator expression layer
  (`_temporal_comparisons.py` helper + `_operators.py` dispatch); it emits
  SQLFunctionCall/SQLBinaryOp/SQLCast nodes only — no SQLRaw, no to_sql(),
  no boundary violation.
- Generality: dispatch is driven by a reusable point-kind classifier
  (`_interval_scalar_point_kind` reusing `_numeric_interval_point_kind`),
  covering `start of` / `end of` / `point from` / `width of` / `Size` over
  Integer/Long/Decimal/mixed/Quantity intervals, both operand orders, and
  +,-,*,/ — not special-cased to the reproducer. Temporal intervals are
  explicitly excluded (None) so DQM's temporal decomposition is untouched
  (confirmed empirically: DQM 47/47 on final tree).
- No silent fallbacks: numeric kind fails fast into numeric SQL; quantity
  kind reuses the existing `_quantity_operand_for_arithmetic` conversion
  rather than coercing through strings.
- Consistency: DECIMAL(38,10) mirrors the existing `_numeric_point_compare`
  precedent for numeric interval point handling.
- Minor debt (logged, not fixed — audit discipline): the +,- and *,/ blocks
  now carry two near-identical scalar_kind gates; a future unification of
  the four-operator dispatch would remove the duplication. Also
  `_is_cql_date_expression` still over-matches `start of`/`end of` on
  unknown point types — acceptable because the numeric gate runs first, but
  worth folding into the classifier if temporal typing of interval scalars
  is ever needed.

## QA Enforcer Gate
QA was thorough: 69 translated assertions x 3 engines covering every
mandate corner (properly-includes open/closed matrix, precision
uncertainty, union chains, successor adjacency at 1e-8/ms, temporal
Size/Width typed errors, width-vs-size per type, point-from unit intervals,
sentinel arithmetic, starts boolean chains, prior-fix re-verification).
Oracle corrections were spec-verified, and the one doctrine collision
(QA-002) was resolved against the pinned fixture rather than prose.
No RETRY_QA.

## Validation (fresh, final tree)
- Master gate: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, OVERALL 2832/2832 — no retry needed.
- Focused: part3 parity 11/11 (incl. new regression test), part2 + v2
  expressions + overlap decomposition + interval UDFs 227/227.
- Binaries unchanged (translator-only fix): cql.duckdb_extension md5
  3e7d4167143e01907fdd8561db43b7d7 (repo bundle == site-packages);
  fhirpath site-packages 57d0634b6ee6eddee9fc06a1355bef5a.

## Issues
QA-001 HIGH RESOLVED/VERIFIED (interval-scalar arithmetic misrouting);
QA-002 MEDIUM INTENDED (exact overflow doctrine, NOT A BUG registry);
QA-003 LOW UNCONFIRMED (point-from null vs run-time error, flagged for
human). Zero non-terminal CRITICAL/HIGH/MEDIUM issues remain.

## Recommendation
Clean exit at iteration 1 (min_iterations=1). Candidate follow-up: unify
the +,-,*,/ quantity/interval-scalar dispatch blocks; human decision on
point-from error-vs-null surface contract.
