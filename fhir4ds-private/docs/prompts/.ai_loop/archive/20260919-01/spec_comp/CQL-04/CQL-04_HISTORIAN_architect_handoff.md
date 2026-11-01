# Architect Handoff — CQL-04 HISTORIAN (iteration 1, 2026-08-20)

## Structural audit of this iteration's fix

QA-001 (HIGH): unary `not` precedence. Fix audit result: CLEAN.

- **Golden standard applied**: the CQL parser's precedence chain
  (implies → or/xor → and → not → equality → comparison → … → unary)
  must mirror the official CQL 1.5 grammar `expression` rule alternative
  ordering. It now does; the change is level-generic (no operator- or
  fixture-specific special-casing), parser-layer only, and both engine
  paths share the parser so lockstep requirements are trivially met
  (no evaluator.cpp change → no extension rebuild mandate).
- **Generalizability**: `parse_not_expression` handles the full operand
  grammar at its tier (comparisons, membership, between, is-null,
  recursion for `not not`), not just the reproducer shapes.
- **No silent fallbacks introduced**; `not 1` still raises a typed
  TranslationError (static Boolean typing preserved).
- **State hygiene**: QA-001 tombstoned below; full evidence in
  ARCHIVE_LOG.md and this file set.

## QA quality gate (QA Enforcer)

QA was NOT lazy: it anchored on the official grammar artifact rather than
re-running the prior SKEPTIC truth tables, discovered a genuinely new
HIGH divergence, verified both engine paths, and correctly triaged the
null→FALSE population-surface rows as pinned doctrine instead of re-lodging
them. No RETRY_QA.

## Iteration summary

- Issues: 1 HIGH (QA-001 not-precedence) — RESOLVED and verified
  (reproducer passes; CQL pytest 5710 passed/9 skipped; conformance
  2832/2832 — ViewDef 144, FHIRPath 935, CQL 1706, DQM 47; baseline held).
- 0 non-terminal CRITICAL/HIGH/MEDIUM issues remain; iteration 1 ≥
  min_iterations 1 → CLEAN exit.
- Files changed: `fhir4ds/cql/parser/parser.py` (fix),
  `fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py`
  (regression test), `fhir4ds/cql/AGENTS.md` / loop `GLOBAL_KNOWLEDGE.md` /
  `ARCHIVE_LOG.md` (institutional memory).

## Issue tombstone

- id: QA-001, status: RESOLVED, verified_in: iteration 1 (CQL-04 HISTORIAN)
