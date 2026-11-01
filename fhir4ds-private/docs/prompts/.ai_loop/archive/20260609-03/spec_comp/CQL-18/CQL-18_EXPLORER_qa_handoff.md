# QA Handoff - CQL-18 EXPLORER

Personality: EXPLORER
Chunk: CQL-18, List Operators Part 1

## Spec Basis

I checked the current CQL Reference v1.5.3 Appendix B list operators. `IndexOf`
uses list equality semantics to locate the element and returns `-1` only when
no element is found. The same reference defines equality as true for equal,
false for known unequal, and null otherwise; incompatible Quantity dimensions
such as `cm` vs `cm2` make equality unknown/null.

## Probe

Fresh probe: `.temp/qa/cql18_explorer_probe.py`

The probe stresses direct helpers and translated CQL across forced Python,
native-loaded, and no-Python C++/macro registrations:

- `CQLIndexOf([parse_quantity('1 cm')], parse_quantity('1 cm2'))`
- `CQLIndexOf([Code missing display], Code with display)`
- translated `IndexOf({ 1 'cm' }, 1 'cm2')`
- translated `IndexOf((from { 1 'cm' } Q return Q), 1 'cm2')`
- compatible Quantity and ordinary missing-element controls

## Finding

`QA-001` HIGH: `IndexOf` collapsed unknown element equality to "not found" and
returned `-1` for incompatible Quantity and unknown clinical Code equality. The
translated query-list form also passed a row subquery directly into
`CQLIndexOf`, producing a DuckDB binder error instead of folding the query rows
into a list.

Initial direct repro before remediation:

- `CQLListContainsEq([1 cm], 1 cm2)` returned `NULL`
- `CQLIndexOf([1 cm], 1 cm2)` returned `-1`
- all three registrations matched the incorrect result

## Handoff

Remediation should make `CQLIndexOf` return the first true equality position,
return `NULL` if no true match exists but any element equality is unknown, and
return `-1` only when every comparison is known false. The translator should
fold query-produced list rows into a DuckDB list before calling `CQLIndexOf`.
