
## SOF-VD-07 EXPLORER QA-001 (2026-08-23) — RESOLVED iteration 1
- HIGH SPEC_VIOLATION: FHIRPath navigation (Python fallback) silently dropped
  genuine elements whose ONLY key is `extension` (valid FHIR: backbone
  elements, nested Extension wrappers), corrupting SQL-on-FHIR repeat row
  counts. repeat['extension'] on [a, b, wrapper{extension:[c]}] emitted 2 rows
  instead of 4; repeat->forEach stacks returned 0 rows.
- Root cause: apply_parsed_path (fhir4ds/fhirpath/__init__.py) top-level
  post-filter matched shadow primitive-extension nodes BY KEY SHAPE
  (data.keys()==['extension']) instead of by provenance.
- Fix: flag synthesis — `_is_shadow_extension = True` on nodes built purely
  from `_field` data in create_reduce_member_invocation
  (fhir4ds/fhirpath/engine/evaluators/__init__.py); both top-level filters now
  check the flag. Shadow `_birthDate`-style nodes still hidden; native C++
  evaluator already returned extension-only elements, so the fix restores
  native-vs-fallback parity (verified via allow_unsigned_extensions LOAD).
- Regression: fhir4ds/viewdef/tests/unit/test_repeat.py (7 tests).
- Post-fix gates: pytest fhirpath+viewdef 1440 passed / 6 pre-existing failures
  (uncommitted FP-18 native div/mod parity tests, absent at HEAD); ViewDef
  conformance 144/144; master run_all 2832/2832. Extension binary unchanged
  (md5 57d0634b6ee6eddee9fc06a1355bef5a repo==site-packages).
- QA-002 LOW INTENDED: deep-tree repeat O(n^2) per-node subtree serialization
  is inherent to value-based union dedup; correct at depth 3000/6000.
