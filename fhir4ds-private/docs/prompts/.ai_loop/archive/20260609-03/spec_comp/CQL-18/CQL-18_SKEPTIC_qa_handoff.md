# QA Handoff: CQL-18 SKEPTIC

## Scope

SPEC COMPLIANCE CHUNK CQL-18: CQL List Operators Part 1.

Items probed: Contains(list, element), Distinct(list), Equal(List),
Equivalent(List), Except(List), Exists(list), Flatten(list), First(list),
In(element, list), Includes(list), Included In(list), IndexOf(list, element),
and Intersect(List).

## SKEPTIC Hypotheses

1. Query or alias produced lists may lose element type evidence and fall back to
   raw DuckDB equality.
2. Clinical Code/Concept equivalence inside lists may ignore CQL clinical
   equivalence rules after list transport.
3. Null list vs empty list vs list containing nulls may diverge between
   translated CQL, forced Python fallback, native-loaded registration, and
   no-Python C++ runtime.
4. Quantity list set operators may drop Quantity JSON shape and compare only
   scalar values.
5. Direct helper macros may behave differently from translated SQL for list
   equality/equivalence and set operations.

## Spec Basis

Current CQL Reference v1.5.3 says list equivalence compares corresponding
elements in order using element equivalence. The same appendix says Code
equivalence is based on code and system only, ignoring display/version, and
Concept equivalence is a non-empty intersection of contained Codes.

## Fresh Probe

Probe file: `.temp/qa/cql18_skeptic_probe.py`

The probe compared forced Python fallback, native-loaded registration, and
no-Python C++ runtime. Most targets matched expected behavior: list equivalence
is order-sensitive, null-list handling for Exists/Flatten/First/Intersect is
aligned, Quantity Intersect/Except preserves Quantity shape, and Code equality
in Contains/Distinct remains display-sensitive.

## Finding

`QA-001` HIGH: list element equivalence over transported Code/Concept JSON
falls back to raw JSON equality.

Evidence:

`(singleton from { { "Code A" } }) ~ (singleton from { { "Code B" } })`
returned `false` across forced Python fallback, native-loaded registration, and
no-Python C++ registration when both Codes shared code/system and differed only
in display. Direct `CQLListEquivalentEq([Code JSON A], [Code JSON B])` also
returned `false`.

Expected: `true`, because the list elements must be compared with CQL
equivalence and Code equivalence ignores display/version.

`QA-002` HIGH was found during focused remediation validation: list equality
for `{ 1 'g' } = { 1000 'mg' }` was intercepted by scalar Quantity comparison
and returned SQL NULL instead of true. Expected: CQL list equality compares
corresponding elements, and Quantity element equality is unit-aware.

## State

`evolution.json` was updated with both issues, both have since been fixed and
verified, and the workflow advanced to `ARCHITECT`.
