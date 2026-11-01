# QA Handoff: CQL-09 SKEPTIC

Scope: CQL comparison operators (Between, Equal, Equivalent, Greater, GreaterOrEqual, Less, LessOrEqual, NotEqual, NotEquivalent) with native-loaded and forced Python fallback DuckDB registrations.

Spec source consulted: CQL Reference v1.5.3 Appendix B, Comparison Operators. Relevant normative points: `between` returns null if any argument is null and interval-valued `between` means included-in an inclusive interval from the bounds; Ratio equality is component-wise Quantity equality and Ratio equivalence compares represented ratio value.

Hypotheses tested:
- SQL `AND` lowering of `between` may let FALSE dominate a null argument. Confirmed.
- Interval-valued `between` may reuse scalar comparison lowering. Confirmed.
- Ratio comparison may fall through to raw JSON/string comparison. Confirmed.
- Temporal imprecision comparisons may fall through to lexical comparison. Disconfirmed for Time/Date literals; precision-aware UDFs returned NULL.
- List/tuple null equality may confuse SQL null semantics. Disconfirmed for probed list/tuple cases.

Evidence: `.temp/qa/cql09_skeptic_probe.py` captures the failing cases and expected results for verification after remediation.

Issues opened: QA-001, QA-002, QA-003.
