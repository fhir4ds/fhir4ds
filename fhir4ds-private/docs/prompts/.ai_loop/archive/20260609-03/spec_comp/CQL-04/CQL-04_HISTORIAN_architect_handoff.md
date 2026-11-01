# Architect Handoff - CQL-04 / HISTORIAN

## Structural Audit

Golden standard written to `.temp/architect/golden_standard.md`.

The remediation is structurally aligned with the translator architecture:

- QA-001 keeps logical operator validation in semantic AST/type inference, before SQL lowering, and avoids adding SQL-string guards or helper-specific hacks.
- QA-002 reuses the existing patient-correlation abstraction and cte_manager convention that unresolved Patient-context references use deferred `_pt.patient_id`.
- Regression tests exercise native-loaded and forced Python fallback registrations, while the fresh probe also checks no-Python C++ direct logical helper parity.

## QA Audit

QA was sufficient for the CQL-04 HISTORIAN role. It covered official truth tables, null three-valued behavior, precedence, `between ... and ...`, invalid operands, typed/`as Any` metadata, translated scalar SQL, translated query `let`/`where`/`return` population SQL, native-loaded registration, forced Python fallback registration, and no-Python C++ direct helper surfaces. `RETRY_QA` is not set.

## Issue Summary

- `2` HIGH issues found.
- `2` resolved.
- `0` open.

## Recommended Fix Order

No further engineer phase is required for this pass. Future CQL logical changes should keep the `as Any` invalid-operand and singleton-from patient-correlation tests in `test_logical_parity.py` as mandatory regression gates.
