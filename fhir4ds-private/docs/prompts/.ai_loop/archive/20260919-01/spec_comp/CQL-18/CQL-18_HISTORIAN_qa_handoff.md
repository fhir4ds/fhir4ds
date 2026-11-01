# QA Handoff — CQL-18 re-launch (HISTORIAN), iteration 1

Chunk: CQL 1.5 List Operators Part 1. Personality: HISTORIAN.
Spec verified live (cql.hl7.org 2019May Appendix B §10.x) plus the official
HL7 cql.g4 grammar (local copy at .temp/qa/cql04_explorer2_2026_08_20/cql.g4).

## Re-verification of SKEPTIC fixes (regression check)
All 17 SKEPTIC probe4 direct dynamic cases still pass (py==cpp): exists,
contains, distinct, Count(distinct), in, IndexOf, =, ~, except, intersect,
includes-vs-static, included-in-vs-dynamic, flatten, First, address/telecom
variants. No regression from the centralized _promote_fhirpath_text_list.

## Verified conformant (no action)
- `X not in Y` ParseError is CORRECT: official cql.g4 has no `not in`
  production — negation is `not (X in Y)` (grammar line 323 only `('in'|'contains')`).
- includes/included-in over static lists and dynamic-vs-static: conformant.
- exists over retrieves (plain and code-filtered): conformant.
- flatten 3-level static, distinct temporal static, First/In dynamic strings.

## Issues found (all translator-level; py==cpp identical)
- QA-001 CRITICAL: define-alias of a multi-valued FHIR property truncates to
  scalar (`define G: Patient.name.given` -> G='Jim'). distinct G -> ['Jim']
  (expected ['Jim','Peter']), Count(G)=1 (direct=3), and except/intersect/=
  /~/included-in/flatten over the alias all raise BinderExceptions. The
  SKEPTIC promotion only rewrites raw 2-arg fhirpath_text calls at operator
  dispatch; alias-bound operands lose the list shape before dispatch.
- QA-002 HIGH: `A includes B` with BOTH operands dynamic lowers to
  intervalContains(fhirpath_text, fhirpath_text) -> false. Same-list includes
  must be true (§10.10). Static/dynamic mixes are fine; the both-dynamic
  shape routes to the interval dispatch.
- QA-003 HIGH: First over a String returns the first character:
  First('final') -> 'f', First(O.status) -> 'f'. First(List<T>) has no String
  overload (§10.8); strings must not be treated as char lists. Silent wrong
  answer, static and dynamic.
- QA-004 MEDIUM: retrieve-alias multi-valued navigation truncates:
  Count(O.component) -> 1 (COUNT(*) over source rows) instead of 2 elements;
  '29463-7' in O.component.code.code -> false with data present.

## Probes
.temp/qa/cql18_historian/probe1.py (adjacent-surface sweep, 29 cases),
probe2.py (drill-down), probe3.py (SQL inspection + code navigation).
