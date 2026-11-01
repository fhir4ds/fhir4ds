# QA Handoff — SOF-SQ-02 launch 3 (EXPLORER)

Date: 2026-08-24. Chunk: SQL-on-FHIR Analytics Layer — runner materialization, parameter binding, DuckDB execution semantics.

## What was probed (all end-to-end against real DuckDB 1.5.2, native + Python fhirpath paths)

- Parameterized body forms: `:name` (spec-example syntax), `$name`, `?`-positional, mixed; same param referenced 3×; None/null values; extra params.
- Result-shape fidelity: DATE/TIMESTAMP params flow as typed datetime columns; microsecond precision; tz-aware datetimes; negative times; '24:00:00' time.
- Unicode/emoji round-trip.
- Multi-statement/DDL-in-content bodies.
- Dependency graph: 30-deep SQLView→VD chain (correct, 0.02 s), idempotent re-execution, rebuild after mid-chain DROP VIEW, interleaved queries sharing one connection, 2-node cycle and self-cycle (both raise SQLQueryCycleError), VD materialization through SQLGenerator with fhirpath UDFs registered.

## Findings

- QA-001 HIGH (OPEN): official spec-example SQL bodies use `:city`-style placeholders (sql-query-examples.fsh; SQL Annotations doc). Runner passes the body straight to `con.execute(sql, dict)`; DuckDB only accepts `$name`/`?`, so spec-example bodies fail with a raw ParserException. Needs safe `:name` → `$name` placeholder rewrite (literals/comments/`::`-cast aware); values still bound via prepared statement, never interpolated.
- QA-002 HIGH (OPEN): tz-aware native datetime params bind host-timezone-dependently and inconsistently with the string path for the same instant (native 10:30+00:00 → 05:30 on host tz -5; string → 10:30). Silent wrong data. Fix: normalize aware datetimes to naive wall time (matches string-path semantics), deterministic across hosts.
- QA-003 LOW: mixed named+positional and positional-only bodies raise raw duckdb errors. Named-only is a defensible implementation decision (prior launch adjudication); document.
- QA-004 LOW: CAST('24:00:00' AS TIME) returns a str in duckdb 1.5.2 (engine quirk); pass-through. NOT-A-BUG (upstream).

## Passers (no action)

30-deep chain correctness+perf, idempotent re-run, re-materialization after DROP, interleaved execution, cycle/self-cycle detection, None binding (SQL NULL), param reuse, emoji round-trip, typed DATE/TIMESTAMP result columns, microsecond fidelity.

Baseline at start: sqlquery suite 94/94, gate 2832/2832 (per handoffs).
