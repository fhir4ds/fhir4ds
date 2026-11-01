# QA Handoff - FP-14 EXPLORER

Spec focus: FHIRPath Normative Release Section 6.2 Comparison (`>`, `<`, `<=`, `>=`).

Direct spec grounding:
- Section 6.2 defines ordering for String, Integer, Decimal, Quantity, Date, DateTime, and Time; empty operands propagate empty; operands must be singleton; operand types must match or be implicitly convertible.
- Quantity comparison requires compatible dimensions; calendar durations and definite UCUM durations above seconds are un-comparable, while seconds can compare.
- Partial Date/DateTime/Time comparisons return empty when precision differs after all shared fields match.
- DateTime timezone handling must respect offsets. The spec allows implementation policy for DateTime values without offsets, but native and forced Python fallback should not expose different policies for the same DuckDB API.

EXPLORER probe:
- Wrote `.temp/qa/fp14_explorer_probe.py` and `.temp/qa/fp14_explorer_probe.log`.
- Covered pathological comparisons inside `where()`/`select()`, nested FHIR Quantity objects, incompatible Quantity dimensions, partial Date/DateTime/Time precision, timezone offsets, empty operands, literal and data-dependent multi-item operands, mixed-type comparisons, Boolean ordering, and reverse operators.
- Compared DuckDB native C++ extension and forced Python fallback.

Finding:
- `QA-001` MEDIUM backend parity issue: one-sided DateTime timezone comparisons diverge between native and fallback. Reproducer: `@2017-11-05T01:30:00.0-04:00 >= @2017-11-05T01:30:00.0` is true in native but false in forced fallback; the reverse `<` case differs in the opposite direction.

Other probed boundaries matched expectations:
- Boolean ordering is rejected/row-resilient.
- Literal multi-item comparisons are invalid for `fhirpath_is_valid()`.
- Calendar-vs-UCUM year ordering returns empty; second-based duration comparison works.
- Nested Quantity path comparison and incompatible dimensions match native/fallback.
