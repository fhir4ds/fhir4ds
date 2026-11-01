# QA Handoff - CQL-09 HISTORIAN

Personality: HISTORIAN

Scope: CQL comparison operators: Between, Equal, Equivalent, Greater,
GreaterOrEqual, Less, LessOrEqual, NotEqual, NotEquivalent.

Spec anchor: CQL 1.5.3 Appendix B comparison operators. Ordered comparisons
are defined for Integer, Long, Decimal, Quantity, Date, DateTime, Time, and
String; the Ratio comparison note says relative Ratio comparisons are not
directly supported.

Probe written:
- `.temp/qa/cql09_historian_probe.py`

Finding:
- `QA-001` HIGH: unsupported ordered comparisons for Ratio/List/Tuple/Interval
  fall through to DuckDB comparison semantics. Ratio comparisons route through
  a Quantity probe and then string comparison, producing arbitrary Booleans;
  list and tuple `>` also return Booleans from DuckDB native ordering.

Evidence before remediation:
- `ToRatio('1 ''mg'':8 ''mg''') > ToRatio('2 ''mg'':16 ''mg''')` returned
  `False` rather than NULL/unsupported.
- `ToRatio('1 ''mg'':8 ''mg''') < ToRatio('2 ''mg'':16 ''mg''')` returned
  `True` from SQL text fallback.
- `{1, 2} > {1, 1}` and `Tuple { Id: 2 } > Tuple { Id: 1 }` returned `True`.

Expected remediation:
- Ordered comparisons (`<`, `<=`, `>`, `>=`) over statically known unsupported
  structural operands should return SQL NULL at the translator boundary instead
  of falling through to DuckDB ordering.
- Preserve supported Quantity and String ordering.
