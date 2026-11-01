# QA Handoff: CQL-15 HISTORIAN

## Scope

SPEC COMPLIANCE CHUNK CQL-15: CQL Interval Operators Part 1.

Personality: HISTORIAN.

Spec anchor: current CQL Reference Appendix B interval operators, especially
Contains, In, End, Ends, Equal, Equivalent, Except, Expand, and Includes.

## Fresh Probe

Created and ran `.temp/qa/cql15_historian_probe.py`.

Covered:
- direct public interval helper/UDF surfaces on forced Python fallback, native-loaded registration, and no-Python C++;
- translated CQL execution on all three runtime paths;
- null container/list/interval rules;
- open and unbounded endpoints;
- inclusive/exclusive interval boundaries;
- interval equality/equivalence through semantic start/end boundaries;
- interval set-operation output shape feeding downstream containment;
- Quantity interval contains/includes/expand behavior.

## Finding

`QA-001` HIGH, SPEC_VIOLATION:

CQL interval/list null-container semantics were not preserved. The CQL Reference
states that `contains` over a null first argument returns false while a null
point returns null, and `in` over a null interval/list argument returns false.

Reproducers before remediation:
- `null contains 5` translated to `system.contains(NULL, 5)` and returned SQL NULL.
- `5 in (null as Interval<Integer>)` translated to SQL `IN` over NULL and returned SQL NULL.
- direct public `intervalContains(NULL, '5')` returned SQL NULL on the no-Python C++ surface.
- untyped `Interval[null, null] contains 5` returned SQL NULL instead of false.

`Interval[1, 10] contains null` already behaved correctly as SQL NULL.

## Handoff

Proceed to remediation for `QA-001`.
