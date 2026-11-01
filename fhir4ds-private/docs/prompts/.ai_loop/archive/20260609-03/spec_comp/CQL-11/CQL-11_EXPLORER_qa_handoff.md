# QA Handoff: CQL-11 EXPLORER

Scope: CQL arithmetic operators part 2 (`Maximum`, `Minimum`, `Modulo`, `Multiply`, `Negate`, `Precision`, `Predecessor`, `Power`, `Round`, `Subtract`, `Successor`, `Truncate`, `TruncatedDivide`).

Spec sources checked:
- CQL Logical Specification v1.5.3 MaxValue/MinValue, Modulo, Multiply, Predecessor, Successor, Truncate, and TruncatedDivide sections.
- CQL Reference Appendix B Arithmetic Operators.

Fresh probe:
- `.temp/qa/cql11_explorer_probe.py`

Findings:
- `QA-001` HIGH: `maximum Quantity` and `minimum Quantity` translate to SQL `NULL`, while the current logical spec defines Quantity max/min as representable Quantity values with default unit `1`. Unsupported max/min types such as `String`, `Code`, and `Concept` also translate to `NULL` instead of raising a translation error.
- `QA-002` HIGH: no-Python C++ `predecessorOf/successorOf(VARCHAR)` treats integer-looking numeric strings as Integer and can overflow-wrap at int64 boundaries. Forced Python and native-loaded registration treat public numeric strings as Decimal and step by `10^-8`; typed Integer/Long still use their numeric overloads.

Validation status:
- Probe currently fails at `QA-001` before remediation, as expected.
