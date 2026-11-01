# Engineer Handoff — CQL-19 launch, iteration 1 (SKEPTIC fixes)

All five QA issues CONFIRMED and RESOLVED at the translator level (py == cpp ==
no-python identical before and after — no native code changed this launch, so
extension binaries untouched: cql md5 3e7d4167143e01907fdd8561db43b7d7,
fhirpath md5 57d0634b6ee6eddee9fc06a1355bef5a, repo bundle == site-packages).

## Root cause
The CQL-18 `_promote_fhirpath_text_list()` machinery covered the Part-1 list
family only. The Part-2 family (Length/Tail/Skip/Take/SingletonFrom/Union/
ProperlyIncludes/ProperlyIncludedIn) received the scalar first-node-truncated
`fhirpath_text` lowering or rows-shaped define/CTE references.

## Fixes (all in fhir4ds/cql/translator/)
1. expressions/_functions.py — `_translate_function_ref`: promote args[0] of
   First/Last/Length/Tail/Skip/Take/SingletonFrom to the list projection
   (QA-001/002/005); skip AST inlining AND rows-coercion for stored-list
   define aliases (`Tail(G)`/`Length(G)`/`Take(G,2)` were []/1/nested).
2. expressions/_lists.py — `_apply_singleton_from`: fhirpath_text branch now
   promotes and re-dispatches into the cardinality CASE (0 -> null, 1 ->
   element, >1 -> typed `SingletonFrom:` error) instead of Malformed-JSON
   json_array_length over plain text (QA-005). Also `_translate_skip/take`
   promote their source (method-syntax forms).
3. expressions/_operators.py — properly includes / properly included in:
   pre-gate promotion of fhirpath_text operands (was falling through to
   intervalProperlyContains -> silently false, QA-004) plus widened
   `_properly_is_list` recognition so the element overload (contains AND
   len>1) is selected for promoted from_json lists.
4. expressions/_operators.py — `_translate_union_op`: new
   `_union_operand_as_list` normalization (stored-list define identifiers -> 
   scalar list value; property paths -> LIST usage; fhirpath_text ->
   promotion), `_as_subquery` star-widening and rows-UNION cases now gated on
   the rows flags, and a new Case 6c list-list branch (Distinct(list_concat)
   with null-as-empty CASE arms) replacing the jsonConcat fallback that
   nested list-in-list (QA-003).
5. translator.py — define-level: a list-union define whose result SQL is
   list-returning reuses the navigation-list stored-list path (List<Any> +
   PATIENT_SCALAR) so the population wrap does not LIST()-aggregate it into a
   nested list.

## Validation
- Probe batteries (static 66 cases + 3VL + dynamic 27 cases):
  .temp/qa/cql19_skeptic/{probe1_final.out,probe2_final.out} — zero
  divergences; only remaining ERR is the spec-mandated SingletonFrom
  run-time error for >1 elements.
- Focused suites: test_list_part2_parity.py 29/29 (16 new end-to-end
  dynamic-operand regression tests appended), test_list_part1_parity.py,
  test_v2_expressions.py 147/147.
- Master conformance gate (incl. DQM final-state): see architect handoff
  (gate1.log in .temp/qa/cql19_skeptic/).

Issue statuses: QA-001..QA-005 RESOLVED (VERIFIED once gate holds).
