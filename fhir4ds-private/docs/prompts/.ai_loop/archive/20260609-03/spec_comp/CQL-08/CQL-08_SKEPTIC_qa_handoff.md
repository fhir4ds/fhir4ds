# QA Handoff - CQL-08 SKEPTIC

Scope: CQL nullological operators (`Coalesce`, `IsNull`, `IsTrue`, `IsFalse`) across translated CQL and public DuckDB helper surfaces, comparing native-loaded and forced Python fallback registrations.

Spec basis: CQL 1.5.3 Appendix B defines `Coalesce<T>` scalar overloads for 2 through 5 arguments plus a single `List<T>` overload; it returns the first non-null value or null if all are null. `IsNull` accepts `Any`; `IsTrue` and `IsFalse` are Boolean predicates that only return true for exact true/false values.

Findings:
- `QA-001` HIGH: `Coalesce((from {null as String, 'x'} V return V))` raises a scalar-arity `TranslationError` even though the query expression is a CQL list and should use the single-list overload.
- `QA-002` MEDIUM: direct public `Coalesce` accepts invalid scalar arities: one-scalar and more-than-five scalar calls return a value in both native-loaded and forced Python fallback registrations.

Probe: `.temp/qa/cql08_skeptic_probe.py` currently fails with both findings.
