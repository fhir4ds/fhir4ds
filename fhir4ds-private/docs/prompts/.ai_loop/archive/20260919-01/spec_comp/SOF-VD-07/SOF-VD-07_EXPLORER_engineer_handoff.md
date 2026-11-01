# Engineer Handoff — SOF-VD-07 EXPLORER (iteration 1)

## QA-001 (HIGH) — RESOLVED
Root cause: `apply_parsed_path` (fhir4ds/fhirpath/__init__.py) filtered
top-level result items by KEY SHAPE (`data.keys() == ['extension']`), which
dropped genuine FHIR elements whose only content is an `extension` (valid:
backbone elements, nested Extension wrappers), not just the `_field`
primitive-extension shadow nodes it was written to hide. This silently removed
rows from ViewDefinition `repeat` output (and repeat->forEach stacks).

Fix (minimal, flag-based):
- fhir4ds/fhirpath/engine/evaluators/__init__.py
  (`create_reduce_member_invocation`): nodes synthesized purely from `_field`
  shadow data are flagged `_is_shadow_extension = True` (both synthesis sites:
  list-zip slot where the main value is None, and the toAdd_-only branch).
- fhir4ds/fhirpath/__init__.py: both top-level filters now check the flag via
  `getattr(item, "_is_shadow_extension", False)` instead of key shape.

Spec grounding: SQL-on-FHIR v2 Select.repeat — the runner recursively follows
each path and collects every matching element; FHIRPath navigation must return
all child elements. Extension-only elements are valid FHIR and must appear.

Regression tests: fhir4ds/viewdef/tests/unit/test_repeat.py (7 tests, all
pass) — navigation keeps extension-only elements, shadow `_birthDate` still
hidden, repeat collects wrapper + nested nodes, repeat->forEach reaches nested
extension, union dedup across multiple repeat paths, subtree-isomorphism dedup,
%rowIndex under repeat.

## QA-002 (LOW) — INTENDED (perf observation)
Deep-tree repeat is O(n^2) (per-node subtree serialization required by the
value-dedup union doctrine). Correct at depth 3000/6000. No fix.

## Validation
- New tests: 7/7 pass.
- pytest fhir4ds/fhirpath/tests + fhir4ds/viewdef/tests: 1440 passed, 6 failed
  — all 6 are TestDualEngineParity cases in
  fhir4ds/fhirpath/tests/unit/test_fp18_math_operators.py, which exists only
  in the uncommitted working tree (absent at HEAD db1e4164) and concerns
  native long-integer div/mod parity — unrelated to this chunk's navigation
  change. Pre-existing before this launch.
- Master gate (final tree, PYTHONPATH=/mnt/d/fhir4ds):
  ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47,
  OVERALL 2832/2832 — baseline holds.
- No native/C++ changes; bundled fhirpath.duckdb_extension md5
  57d0634b6ee6eddee9fc06a1355bef5a matches between repo bundle
  (fhir4ds/fhirpath/duckdb/extensions/) and user site-packages
  (~/.local/lib/python3.10/site-packages/fhir4ds/...). No redeploy needed.
