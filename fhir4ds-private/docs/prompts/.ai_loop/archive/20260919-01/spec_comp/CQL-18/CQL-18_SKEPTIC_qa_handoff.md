# QA Handoff — CQL-18 re-launch (SKEPTIC), iteration 1

Chunk: CQL 1.5 List Operators Part 1 (Contains, Distinct, Equal, Equivalent,
Except, Exists, Flatten, First, In, Includes, Included In, IndexOf, Intersect).
Personality: SKEPTIC.

## Spec verification
Fetched full normative §10 text live this session (cql.hl7.org/2019May
09-b-cqlreference.html). Cross-checked official local fixtures
(fhir4ds/cql/tests/official/cql-tests/tests/cql/CqlListOperatorsTest.xml).

## Verified conformant (no action)
- Static-literal surface: 31/31 probe cases conformant with py == cpp ==
  no-python parity (order-sensitivity of = and ~ on lists, 1.0-in-{1,2},
  empty-list In/Contains/IndexOf(-1)/First(null), null-guard IndexOf,
  set-dedup except/intersect incl. duplicates and null elements, interval/
  time/tuple elements through every operator, Distinct first-occurrence
  order + temporal distinct). Probes: .temp/qa/cql18_skeptic2/probe1.py.
- Null-boundary adjudications (fixtures outrank spec prose): distinct
  {null,null,null} -> {null} (fixture pins dedup of nulls, contradicting the
  spec prose note "multiple nulls preserved" — fixtures win per
  GLOBAL_RULES); null in {1,null} -> true (fixture contradicts spec example
  IsIsAlsoNull; fixture wins); ExceptLeft example pins null-right-operand ->
  left list.
- Existing parity suites green: test_list_part1_parity.py + part2 = 22/22.

## Issues found (all dynamic-FHIR-list translation layer; py and cpp
identical, so this is translator-level, not engine divergence)
- QA-001 CRITICAL: `exists Patient.name.given` -> false with data present
  (fhirpath_bool of a string collection is NULL). Silent wrong answer.
- QA-002 HIGH: `contains` over dynamic list uses substring semantics over
  truncated text: contains 'Ji' -> true, contains 'Peter' -> false.
- QA-003 HIGH: distinct/Count(distinct) dynamic -> GROUP BY BinderException;
  list = / ~ dynamic -> array_length(VARCHAR) BinderException.
- QA-004 HIGH: except/intersect/IndexOf with dynamic list operand ->
  "UNNEST() for correlated expressions is not supported yet".
- QA-005 HIGH: includes/included in with dynamic list -> COALESCE
  VARCHAR vs NULL[] BinderException.
- QA-006 MEDIUM: `flatten { Patient.name.given }` -> flatten(VARCHAR[])
  BinderException (list-literal wrap loses nesting).

Working dynamic surfaces: First, In (exact equality, correct incl. 'Peter').

Handoff to Remediation: reproducer .temp/qa/cql18_skeptic2/probe4.py
(per-define isolation, py+cpp). Root-cause hint: the translator lowers
retrieved multi-valued fields via scalar fhirpath_text/fhirpath_bool instead
of the list-valued `fhirpath(...)` projection (used by First), and the list
macros' unnest-based SQL cannot run against correlated retrieval subqueries.
