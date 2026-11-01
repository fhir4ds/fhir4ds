# QA Handoff — SOF-VD-07 (select.repeat), SKEPTIC, iteration 1

## Spec ground truth (verified from source)
- Canonical SD (HL7/sql-on-fhir main, input/resources/viewdefinition/StructureDefinition-ViewDefinition.xml, element `ViewDefinition.select.repeat`): **0..* string**, "A list of FHIRPath expressions that define paths to recursively traverse. The view runner will recursively follow each path to any depth, collecting results from all levels. All results are combined using a union operation." NOTE: the *released* ig/2.0.0 SD snapshot has NO repeat element (matches SOF-VD-05 doctrine note); repeat lives on main + fixtures.
- Constraint: at most one of forEach / forEachOrNull / repeat per select.

## Probed (all through real pipeline: parse → SQLGenerator(strict) → DuckDB, official-runner SQL adaptation)
1. All 19 repeat.json official fixtures — set-equal to `expect` (order-insensitive per official runner).
2. %rowIndex under repeat: 0-based per repeated row — correct.
3. repeat + where on same select: filters repeated nodes — correct.
4. Overlapping paths `["item","item"]` and `["item","item.item"]`: union dedup collapses re-reached nodes — correct per union semantics.
5. Parser: repeat-as-string, empty repeat array, repeat+forEach / repeat+forEachOrNull all rejected; array-of-non-empty-strings enforced — correct (validate_repeat_paths).
6. Native C++ fhirpath_repeat (binary loaded via allow_unsigned_extensions): correct rows; deep nesting OK to 20k, 100k = OOM kill (quadratic serialized output, inherent).

## Findings
- **QA-001 MEDIUM OPEN** — Python fallback `fhirpath_repeat_udf` SEGFAULTS on deeply nested JSON (~12–15k levels; 10k OK, 15k crash). Root cause: `_eval_with_recursion_budget` / the UDF raise `sys.setrecursionlimit(json_depth*4+1000)` (61k at depth 15k); the recursive `visit()` in fhir4ds/fhirpath/__init__.py (2 Python frames per nesting level) then overflows the 8 MB C stack (CPython 3.10 recurses in C per Python call). Process crash, not graceful error. Faulthandler traceback pins the crash inside visit→get_data recursion. Reproducer: `.temp/qa` probes (nested QuestionnaireResponse chain, repeat ["item"]).
- **QA-002 LOW INTENDED** — value-based union dedup collapses distinct-but-identical sibling nodes (2 identical item subtrees → 1 row). Consistent with FHIRPath `=`-equality union semantics and SOF-VD-05 doctrine (no fixture pins node-identity dedup; upstream SD silent). Do not fix without a fixture pin.
- **QA-003 LOW INTENDED** — repeat output row order is not document order (unnest order). Spec imposes no row order; official runner sorts before compare; doctrine: never order-assert across unnest levels.
- **QA-004 LOW INTENDED** — primitive-yielding repeat paths return empty (pinned SOF-VD-05, reference-impl-consistent).

## Verified-clean (no action)
forEach/forEachOrNull/repeat mutual exclusion, nested repeat (depth 3), repeat under forEach and forEachOrNull, unionAll under/with repeat, sibling repeats, multi-path repeat inside forEach — all covered by passing official fixtures.

Probes: /mnt/d/fhir4ds/.temp/qa/probe.py and inline heredocs.
