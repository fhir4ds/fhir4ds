# Architect Handoff — CQL-11 EXPLORER2 (2026-08-21)

## Scope
Structural audit of this launch's four fixes plus QA-quality gate for chunk CQL-11 (iteration 1).

## Golden-standard invariants applied
1. Translator owns type-sensitive clamping where the runtime erases CQL types (Integer/Long → BIGINT).
2. No silent fallbacks; typed errors over masked defaults.
3. Dual-engine lockstep: every semantic change lands in Python fallback and native-compatible form; parity tests required.
4. No SQLRaw / mid-pipeline to_sql; SQL composed through AST nodes (SQLCase, SQLCast, SQLBinaryOp).
5. Layering: parser/translator/UDF boundaries respected.

## Audit findings
- QA-001 fix (CASE guard in `_operators.py`): composed via AST nodes, no raw SQL; general for the class of statically Integer-typed operands (Coalesce inference recurses, mixed types degrade to plain helper — no over-clamping of Long). Complies with invariant 1. Verified DuckDB Python UDFs cannot be overloaded by signature — translator-level guard is the correct layer.
- QA-002 fix (TRY_CAST BIGINT before unary minus): uses the existing `_uncertain_between_sql_name` recognizer (reuse, no duplication), routes only the two Integer-valued VARCHAR helpers. Binary-consumer symmetry (cqlUncertainAdd) preserved.
- QA-003 fix (`quantityNegate`): preserves representational contract by mirroring native serialization; removed a redundant pint dependency path (also a small perf win — no unit registry load on negate).
- QA-004 fix (parser EOF check): fails fast at the correct layer; no behavior change for well-formed input (5749 CQL tests pass unchanged).

## QA Enforcer Gate
QA was NOT lazy: mandate items (operator chains at extremes, every temporal precision + offsets, Precision overloads, Round negative precision, Modulo/TruncatedDivide sign matrices, Power fractional exponents, Negate on Quantity/temporal, Quantity cross-unit Min/Max, where-clause retrieves with .value guards and alias indirection, E2E DuckDB both engines) were all probed with a dual-engine harness, and spec text was fetched and quoted before logging. RETRY_QA: false.

## Drift log
No new architecture drift. No test-driven hacks introduced (guards are type-class based, not fixture-value based).

## State decision
All issues terminal (VERIFIED). Zero non-terminal CRITICAL/HIGH/MEDIUM remain; iteration >= min_iterations (1); exhaustive_mode false → clean exit. evolution.json set to workflow=null, exit_reason=CLEAN.
