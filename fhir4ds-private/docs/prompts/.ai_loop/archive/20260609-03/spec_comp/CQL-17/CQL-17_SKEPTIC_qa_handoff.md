# QA Handoff: CQL-17 SKEPTIC

Scope: CQL Interval Operators Part 3. I read the current loop state, global
rules/knowledge, root and CQL extension AGENTS, validation procedure, local
official interval XML, and the current CQL Reference interval-operator text.
`docs/architecture/translator/AGENTS.md` and `fhir4ds/cql/AGENTS.md` are not
present in this checkout.

SKEPTIC hypotheses tested with fresh probe `.temp/qa/cql17_skeptic_probe.py`:
- Null interval containers could be confused with typed-null unbounded
  intervals.
- Open integer/decimal singleton intervals could diverge in `point from`,
  `width`, and `size`.
- `intervalUnion` could serialize raw open endpoints and break downstream
  containment.
- Quantity interval width could skip unit conversion or accept incompatible
  units.
- Precision-qualified `properly includes`, `same`, `same or before/after`,
  and `starts` could collapse partial-date uncertainty to false.

Finding:
- `QA-001` HIGH: `intervalProperlyIncludedIn(valid_interval, NULL)` returns
  `TRUE` on forced Python fallback, native-loaded registration, and no-Python
  C++ surface. Translated
  `Interval[1, 5] properly included in (null as Interval<Integer>)` also
  returns `TRUE`. The current CQL Reference says either null argument returns
  null and gives this exact pattern as a null example. Keep
  `Interval[1, 5] properly included in Interval[null as Integer, null as
  Integer]` true; the bug is only a null interval value, not typed-null
  unbounded endpoints.

Other CQL-17 checks in the probe passed before/after this failure.
