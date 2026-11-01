# QA Handoff — CQL-19 launch (SKEPTIC), iteration 1

Chunk: CQL 1.5 List Operators Part 2 (Last, Length, Not Equal, Not Equivalent,
Properly Includes, Properly Included In, Singleton From, Skip, Tail, Take,
Union). Personality: SKEPTIC.

## Spec verification
Fetched normative §10 text live (cql.hl7.org/2019May 09-b-cqlreference.html)
for every operator; cross-checked official local fixtures
(CqlListOperatorsTest.xml) for all null-boundary and properly-includes cases.
Adjudications:
- List union with a null operand returns the OTHER list (current behavior is
  conformant; cql.hl7.org 2019May prose "either null -> null" is stale —
  cqframework/clinical_quality_language issue #887 pins null-as-empty).
- `null properly included in {1,3,5}` -> FALSE per fixtures
  (ProperInNullRightFalse) contradicting the spec prose example; fixtures
  outrank prose, current behavior is INTENDED.
- Skip/Take/Tail null LIST -> null (not empty); null count: Skip -> whole
  list, Take -> empty; negative: both -> empty. All conformant.

## Verified conformant (no action)
- Static-literal surface: 66/66 probe cases conformant across py == cpp ==
  no-python parity (all null-list boundaries, Skip/Take count semantics incl.
  negative/oversized/null, Tail one/empty, Last/Length null elements, union
  dedup incl. null elements + int/decimal promotion + symbolic `|`, !=/!~
  order sensitivity, null propagation verified through `{ (expr) }` lifted
  contexts — properly-includes/includes null-list operands return true null,
  not presence-encoded false).
- Dynamic surfaces already working: Last, Count, !=/!~ list-list over
  Patient.name.given; Last/Length/Tail/Take over Obs alias multi-valued
  navigation (component.code.coding.code).
- Probes: .temp/qa/cql19_skeptic/{harness.py,probe1.py,probe2.py,probe2.out}

## Issues found (all translator-level; py == cpp == nopy — no engine divergence)
- QA-001 HIGH: Length(Patient.name.given) -> 5 (string length of truncated
  first node) instead of 3. Silent wrong answer.
- QA-002 HIGH: Take(dynamic,1) -> 'P' (character slice of VARCHAR);
  Skip/Tail(dynamic) -> BinderException array_length(VARCHAR); Tail over the
  stored-list define alias of a dynamic field -> [] instead of remaining
  elements.
- QA-003 HIGH: union with ANY dynamic list operand fails (list_concat type
  mismatch / CASE VARCHAR[] vs VARCHAR / 'Subquery returns N columns' from
  SELECT * FROM CTE inside the Distinct wrap).
- QA-004 HIGH: properly includes / properly included in over a dynamic
  multi-valued field silently returns False with data present.
- QA-005 MEDIUM: `singleton from Patient.name.given` -> Malformed JSON
  InvalidInputException instead of singleton semantics (P1 3 elems ->
  expected run-time error; P2 no names -> null).

## Root-cause hint for Remediation
CQL-18's `_promote_fhirpath_text_list()` (fhir4ds/cql/translator/expressions/
_utils.py) is applied at Distinct, IndexOf, Equal/Equivalent, Contains, HasAll,
Except, Intersect, Exists, First/Last(list define) and flatten sites — but NOT
in this chunk's family: `_translate_skip_expression` / `_translate_take_expression`
(_lists.py:1063/1073), the Length list branch (_functions.py:1551), Tail (lowers
via Skip), SingletonFrom (_functions.py:2995), `_translate_union_op` list branch
(_operators.py:4121), and the properly-includes dispatch. Mirror the existing
promotion + `_is_list_returning_sql`/`stores_list_value` gating so stored-list
define aliases also route correctly (Tail over alias currently returns []).
