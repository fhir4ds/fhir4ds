# QA Handoff - CQL-18 SKEPTIC

Scope: CQL List Operators Part 1 for `Contains(list, element)`, `Distinct`,
list `=`, list `~`, `Except`, `Exists`, `Flatten`, `First`, `In`,
`Includes`, `Included In`, `IndexOf`, and `Intersect`.

Method: independent fresh probes only. I used the current source tree, the
current official CQL XML at
`fhir4ds/cql/tests/official/cql-tests/tests/cql/CqlListOperatorsTest.xml`,
and a new probe at `.temp/qa/cql18_skeptic_probe.py`. The probe compared
translated CQL on forced Python fallback, native-loaded registration, and
no-Python/browser-style C++ plus pure SQL macros.

Findings:

- `QA-001`: `Except` used DuckDB filtering and preserved duplicates.
  Reproducer: `{ 1, 1, 2, 3 } except { 2 }` returned `[1, 1, 3]`; CQL set
  semantics require `[1, 3]`.
- `QA-002`: `Intersect` used DuckDB `list_intersect`, which dropped null
  intersections. Reproducer: `{ null, 1, 3 } intersect { null, 3, 5 }`
  returned `[3]`; CQL set semantics require `[null, 3]`.
- `QA-003`: Quantity list membership/set operations compared internal Quantity
  JSON literally. Reproducers: `{ 1 'g' } contains 1000 'mg'`, `1000 'mg' in
  { 1 'g' }`, list `includes`, `included in`, `Distinct`, `Except`,
  `Intersect`, and list `=` all needed Quantity equality through
  `quantityCompare(..., '==')`.

Important non-bugs preserved from official XML:

- `{ 'a', 'b', null } contains null` is `true`.
- `null in { 1, null }` is `true`.
- `{ 's', 'a', 'm' } includes null` is `null`.
- `null included in { 2 }` is `null`.
- `IndexOf({ 1, null }, null)` is `null`.

Post-remediation probe status: `.temp/qa/cql18_skeptic_probe.py` passes across
forced Python fallback, native-loaded registration, and no-Python/browser-style
C++ plus pure SQL macros. Architect validation also hardened the same helper
boundary so mixed non-numeric element types compare false instead of relying on
DuckDB coercion or raising conversion errors.
