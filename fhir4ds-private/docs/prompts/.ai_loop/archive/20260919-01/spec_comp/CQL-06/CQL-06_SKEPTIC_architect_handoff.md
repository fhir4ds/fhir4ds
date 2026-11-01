# Architect Handoff — CQL-06 SKEPTIC (iteration 1)

## Scope
Structural audit of the CQL-06 conversion-check fix and the QA/Engineering passes for chunk CQL-06 (CQL 1.5 Type Operators — Conversion Checks).

## Golden Standard invariants applied
1. Conversion grammar acceptance must be data-driven (unit registries), not ad-hoc string matching — SATISFIED: fix gates the bare-token alternative on the existing `_CQL_CALENDAR_DURATION_UNITS` registry; no new hardcoded unit lists.
2. No silent fallbacks masking malformed input — SATISFIED: bare non-calendar tokens ('5 mg', '5 Years', '5 mgx') still rejected (return null/false), not coerced.
3. Dual-path lockstep: native-supplemented and Python-only backends must agree — SATISFIED: both backends share the Python `toQuantity` (native `ToQuantity(VARCHAR)` shadowed per AGENTS.md doctrine); 10-case reproducer + 17-case regression test assert parity.
4. Minimal footprint — SATISFIED: one grammar change in `udf/quantity.py`; no translator or C++ changes needed.

## Audit findings
- Zero new architectural issues. The fix is registry-driven, spec-cited (Appendix B §ToQuantity + Table 9-G round-trip), and covered by a focused parity regression test.
- Observation (no action): raw-UDF `ToQuantity(quantity_json_string)` returns NULL for a Quantity-shaped JSON string (it only accepts Ratio-shaped JSON). The spec has no Quantity overload for ToQuantity, and translated quantity-typed operands route through `parse_quantity`, so this is a non-spec UDF-boundary surface. Noted, not logged.

## QA Enforcer Gate
QA was NOT lazy: ~130 dual-backend probes spanning all 12 operators, null propagation, boundary values, format strictness, UCUM conversion semantics, and end-to-end translation; spec verified from primary sources before logging. The single finding (QA-001) was real, spec-grounded, and is now RESOLVED with baselines green. RETRY_QA: false.

## Empirical validation
- CQL conformance: 1706/1706 (100%) — baseline held.
- DQM: 47/47 (100%) — baseline held.
- Conversion-check parity suite: 8/8 passed.

## Issue summary
- QA-001 (HIGH, SPEC_VIOLATION): RESOLVED — bare calendar-duration keywords now accepted by ToQuantity/ConvertsToQuantity/ToRatio/ConvertsToRatio grammar.

## Recommended Fix Order
None — no open issues. Clean exit at min_iterations (1), zero non-terminal CRITICAL/HIGH/MEDIUM issues.
