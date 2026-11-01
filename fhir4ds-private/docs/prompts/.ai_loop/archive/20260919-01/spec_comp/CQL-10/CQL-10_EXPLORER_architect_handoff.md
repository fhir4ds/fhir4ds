# Architect Handoff — CQL-10 EXPLORER, iteration 1 (2026-08-21)

## Structural health: SOUND for this chunk

Golden standard: `.temp/architect/golden_standard_cql10_explorer.md`
(8 invariants). All satisfied by this iteration's changes:

- **Dual-engine lockstep (inv 1, 2)**: QA-001 fix landed in both
  `fhir4ds/cql/duckdb/udf/quantity.py` (pint `to_reduced_units()`) and
  `extensions/cql/src/cql/quantity.cpp` (`units_compatible` + `to_base`
  ratio → unit `1`); parity asserted per-engine in the new test; extension
  rebuilt, md5 `2722c674ccbdd1e542e4949f8f65c6ae` verified across repo
  bundle and site-packages (cache empty), fix re-verified through reloaded
  cpp connections.
- **No silent fallbacks (inv 3)**: QA-002 extended the typed-guard family to
  Quantity operands/mixtures; 15 invalid cases now raise typed
  TranslationError; 14 valid surfaces (Q/Decimal, scalar*Q, temporal+Q,
  Q/Q, Abs(Q)) explicitly asserted unchanged.
- **Layering (inv 5)**: guards live in the translator expression layer
  (`_functions.py` unary family, `_operators.py` binary guard); no engine
  or SQL-generation layer was touched for the guards.
- **Generality (inv 6)**: fixes address the operand-class semantics, not
  fixture strings; no new hardcoded codes beyond UCUM semantics reuse.
- **Validation (inv 7)**: reproducer tests green (parity file 10/10 incl.
  part2 sweep 19/20 → fixed expectation, final green); full conformance
  2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).

## Findings

- ARCH-001 (LOW, informational): the typed-operand taxonomy is now split
  across two translator sites (`_ARITHMETIC_FN_STATIC_GUARDS` +
  `_ARITHMETIC_FN_QUANTITY_REJECTED` in `_functions.py`; the mixed-scalar
  guard block in `_operators.py`). Behaviorally correct and documented, but
  future operator chunks should consider a single shared operand-type
  policy table to avoid drift. Logged in fhir4ds/cql/AGENTS.md context; no
  fix this iteration (audit-phase discipline).
- ARCH-002 (observation): native `quantity_multiply` for distinct
  commensurable units (`mg * g`) still yields a compound unit without
  conversion — consistent py↔cpp and beyond the reference engine's
  signatures (which rejects Q*Q); no action required for CQL-10.

## QA Enforcer Gate: PASS

EXPLORER QA covered the mandate's full probe matrix (quantity arithmetic
through every operator, temporal/quantity boundary overloads, precision
edges, Exp/Ln/Log domains, Integer/Integer divide, conversion chains,
static-guard interplay, end-to-end retrieve execution), verified against
the live spec and the cqframework reference implementation, dual-engine on
every case, zero py↔cpp divergence. No veto.

## State

Iteration 1 ≥ min_iterations (1); zero non-terminal CRITICAL/HIGH/MEDIUM
issues. Both issues RESOLVED with reproducer tests and the 2832/2832
baseline intact. Recommend CLEAN exit; details archived to ARCHIVE_LOG.md.
