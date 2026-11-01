# QA Handoff - CQL-05 HISTORIAN

Scope: CQL structural type operators (`as`, strict `cast`, `Children`,
`Descendants`, `convert`, `is`) across translated SQL, native-loaded DuckDB
registration, and forced Python fallback.

Spec basis:
- CQL 1.5.3 Appendix B `As`: `as<T>(argument Any)` returns null on runtime
  type mismatch; strict `cast as<T>(argument Any)` throws a runtime error on
  mismatch.
- CQL 1.5.3 Appendix B `Children` / `Descendants`: structured members are
  returned as flattened list values; list-valued members are expanded; null
  source returns null.
- CQL 1.5.3 Appendix B `Is`: runtime type match or derivation returns true,
  otherwise false.

Fresh probe: `.temp/qa/cql05_historian_probe.py`.

Finding:
- `QA-001` HIGH: strict `cast X as T` loses strictness at parse/translation.
  `cast 5 as String` currently translates to `NULL`, exactly like
  `5 as String`, instead of raising the required runtime error. The parser
  accepts the `cast` prefix but returns the same `BinaryExpression(operator="as")`
  used for nullable `as`, so the translator cannot distinguish the two forms.

Non-bug confirmations:
- `Children(null) is null` is true.
- `Children(5)` is an empty list.
- `Children`/`Descendants` flatten tuple/list structured values consistently
  across native-loaded and forced Python fallback registrations.
- Quantity/clinical structural traversal and `is`/`as` checks matched existing
  native/fallback behavior in the fresh probe until the strict-cast failure.
