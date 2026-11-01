# Engineer Handoff — CQL-01 EXPLORER (iteration 1, 2026-08-19)

## Triage
| Issue | Severity | Classification | Outcome |
|---|---|---|---|
| QA-001 alias Decimal arithmetic through DOUBLE | HIGH | SPEC_VIOLATION | RESOLVED |
| QA-002 alias Integer/Long overflow guard bypass | HIGH | SPEC_VIOLATION | RESOLVED |
| QA-003 out-of-extent Decimal literals accepted | MEDIUM | SPEC_VIOLATION | INTENDED (fixture-pinned) |

## Fixes
Both HIGH issues share one root cause in
`fhir4ds/cql/translator/expressions/_operators.py` (arithmetic binary-operator
translation): when one operand is a numeric literal and the other a
definition-alias scalar subquery `(SELECT sub.value FROM "CTE" ...)`, the
subquery was unconditionally wrapped in `TRY_CAST(... AS DOUBLE)`.

Surgical change (`_cast_numeric_subquery`, driven by
`context.definition_meta[cte].cql_type`):
- Decimal alias → `TRY_CAST(... AS DECIMAL(28,8))` — spec-exact 20 integer +
  8 fraction digits; alias-literal arithmetic now exact
  (`define N: M + 0.2` → `0.30000000`, `D + 0.2 = 0.3` → true).
- Integer/Long alias (+,-,*) → compute in `DECIMAL(38,0)` (wide enough for any
  single op over Integer/Long CQL ranges), then narrow the final result with
  `TRY_CAST(... AS INTEGER/BIGINT)` so overflow yields NULL per CQL 1.5 §9.1.1
  (`max-Integer alias + 1` → null, `max-Long alias + 1` → null, in-range
  results keep integral SQL types). NOTE: DuckDB rejects `TRY()` around
  scalar subqueries, so the literal path's TRY-wrap strategy is not usable
  here; wide-compute + TRY_CAST narrowing is the equivalent.
- Unknown-typed subqueries (e.g. `MAX(fhirpath_text(...))`) keep the DOUBLE
  fallback.

QA-003: implemented a strict `(10^28-1)/10^8` extent check first; the recovery
gate caught a regression (CQL conformance 1703/1706 — official
ValueLiteralsAndSelectors fixtures pin 28-int-digit literals as VALID).
Reverted. The pre-existing parser policy (parser.py:1596, ≤28 integer digits,
CQL §2.3) is the correct fixture-compatible boundary; pinned with new tests.

## Files changed
- `fhir4ds/cql/translator/expressions/_operators.py` (alias numeric operand
  typing + result narrowing)
- `fhir4ds/cql/translator/expressions/_core.py` (comment only; extent check
  attempted and reverted)
- `fhir4ds/cql/tests/unit/test_cql01_primitive_types.py`
  (+`TestDefineAliasArithmeticExactness` 6 tests, +`TestDecimalLiteralExtent`
  3 tests; 50 total pass)

## Validation
- Focused: test_cql01_primitive_types.py 50/50.
- CQL unit/integration: 4916 passed, 4 skipped (one transient smoke-gate
  error caused by concurrent conformance run; passes standalone 12/12).
- Full conformance: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, OVERALL 2832/2832 (baseline held).
- Dual-path parity: native-loaded vs forced Python fallback identical on all
  alias-arithmetic cases (probe2 re-run, 0 parity diffs).
