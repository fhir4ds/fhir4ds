# QA Handoff — SOF-VD-09 HISTORIAN (2026-08-23, iteration 1)

Chunk: SQL-on-FHIR v2 root `ViewDefinition.where`. Personality: HISTORIAN.

Spec grounding: SD 2.0.0 (releases/ig/2.0.0 StructureDefinition-ViewDefinition.json —
where 0..* root-only, where.path 1..1 "input context is the collection of
resources", where.description 0..1) and the formal Process(S,N) semantics from
main-branch ViewDefinition-notes.md (columns evaluate as `fhirpath(col.path, f)`
with `f` the iterated focus; the focus-first mixed-context guard doctrine).
Also re-confirmed: SD 2.0.0 has NO select.where element — select-level where is
a fhir4ds draft-spec extension (SOF-VD-06 doctrine).

Probe: `/mnt/d/fhir4ds/.temp/qa/sof_vd09_historian_2026_08_23/probe.py` — 25
assertions, semantic cases on BOTH native C++ extension and forced Python
fallback. 23 passed after pinning two probe bugs (repeat takes an array form;
NH9 expectation corrected once the real defect was characterized below).

Verified conformant (no issue), all native==fallback:
- NH1-NH5: nested/extension where filters at element scope (forEach,
  forEachOrNull), multiple wheres AND-joined, non-boolean excludes, root+where
  composition.
- NH6: unionAll branch where filters per-branch.
- NH7: empty where arrays accepted, no filtering.
- NH8: description retained root+nested via to_dict roundtrip.
- NH10a-e: parser shape corners (empty where item, nested string where, unknown
  nested where field, boolean path, list description) all rejected.
- NH11: runtime-invalid where expression fails loud or excludes, both engines.
- NH12: where inside `repeat` filters rows (array form).
- Root-where scope re-verified: `active = true and %resource.gender = 'female'`,
  `%rootResource.active`, `%context.gender` all correct on both engines.

Issue found (NEW divergence, missed by SKEPTIC):
- QA-001 (HIGH, SPEC_VIOLATION): a column (or extension where) expression that
  STARTS with a `%resource.`/`%rootResource.`/`%context.` prefix and later
  references the CURRENT FOCUS silently evaluates the focus reference against
  the ROOT resource. `forEach: name` + column `%rootResource.gender &
  given.first()` returns 'female' (expected 'femaleAlice'); both engines.
  The reverse ordering correctly raises the typed "mixes built-in
  ViewDefinition contexts" ValidationError — the prefix branch of
  `generator._resolve_environment_path_context` checks only for other builtin
  refs in the tail and never calls `_expression_uses_current_focus`, so the
  guard is order-dependent. Status CONFIRMED in evolution.json.
