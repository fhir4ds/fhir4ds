# QA Handoff — SOF-VD-09 SKEPTIC fresh rerun (2026-08-23, iteration 1)

Chunk: SQL-on-FHIR v2 root `ViewDefinition.where`. Personality: SKEPTIC.

Spec grounding: SD 2.0.0 element defs (ViewDefinition.where 0..* BackboneElement;
where.path 1..1 string; where.description 0..1 string, "Every constraint must
evaluate to true"), Process(S,N) entry step 2 (where evaluated against the ROOT
resource before row generation, after the resourceType check), and the official
validator schema (sof-js/src/validate.js: where = array of objects, required
path, additionalProperties:false).

Probe: `/mnt/d/fhir4ds/.temp/qa/sof_vd09_skeptic_2026_08_23/probe.py` — 32
assertions, run on BOTH native C++ extension and forced Python fallback.

Verified conformant (no issue):
- H1/H1b: multiple root wheres AND-joined; one false excludes the resource.
- H2a-c: false, empty, missing-field (empty), and false values all exclude;
  only exact singleton true includes.
- H3a-d: non-boolean results (string scalar, 'true' literal, numeric,
  multi-item `true | false`) exclude rows — matches "must evaluate to true";
  `fhirpath_json(...) = '[true]'` exactness confirmed on both engines.
- H4: where.description retained via to_dict(); null/numeric description
  rejected at parser.
- H5/H5b2/H5c/H5d: %constants in where incl. backtick %`G` form and constants
  inside where() function args; undefined %constant raises
  ConstantResolutionError. Spaced constant names (%`the gender`) are
  unreachable because Constant.name enforces the SD sql-name constraint
  (correct rejection, verified against SD).
- H6a-d: complex FHIRPath (where().exists(), iif(), comparisons, substring()).
- H7: root where filters BEFORE top-level forEach row generation; %resource
  columns still resolve to the root id.
- H8/H8b: %resource and %rootResource in where target the root resource.
- H9: malformed where (missing/empty/whitespace/null/non-string path, numeric
  description, present-null where) all rejected at parse.
- H10: shared-table resourceType filter + where compose; Observation rows
  excluded.

Issue found:
- QA-001 (MEDIUM, SPEC_VIOLATION): strict parser accepted non-array `where`
  (bare string, single object), list-of-string items, and where items with
  unknown extra keys — diverging from the official validator schema
  (array-of-objects, additionalProperties:false) and FHIR JSON repeating-
  element shape. Same divergence class as the SOF-VD-05 unknown-select-field
  fix. Logged in evolution.json as CONFIRMED.

Behavior note: probe expectation updates during the run (H2c: p2's
active=false is correctly excluded; H6d tuple form) were probe bugs, not
product bugs.
