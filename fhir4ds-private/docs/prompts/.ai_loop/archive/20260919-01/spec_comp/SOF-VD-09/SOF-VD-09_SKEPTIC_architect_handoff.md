# Architect Handoff — SOF-VD-09 SKEPTIC (2026-08-23, iteration 1)

Scope: root ViewDefinition.where chunk. Structural audit focused on the
boundaries touched this launch.

Golden-standard invariants checked (consistent with established doctrine):
1. Official-JSON shape strictness lives at the parser / from_dict boundary;
   permissive normalization (warnings, convenience forms) lives at direct
   dataclass / to_dict / validate_view_definition boundaries. — The QA-001 fix
   preserves this split exactly: strictness added only in `_parse_where`;
   `validate_where_conditions` remains the shared permissive normalizer.
2. Where metadata validation centralized in types.py helpers reused by
   parser, serializer, generator. — Unchanged; `_parse_where` only adds a
   shape preflight before delegating to the shared helper.
3. Where filtering is an exact-singleton-Boolean-true SQL boundary
   (`fhirpath_json(...) = '[true]'`) evaluated against the root resource
   before row generation (Process(S,N) step 2). — Re-verified empirically on
   both engines, incl. root scope under top-level forEach, %resource /
   %rootResource routing, and resourceType-filter composition.

QA quality gate: PASS — 32 hypothesis-driven assertions on both engines,
spec-grounded (SD 2.0.0 element defs + Process(S,N) + official validator
schema), one real divergence found and fixed. No RETRY_QA.

Issues: 1 found (QA-001 MEDIUM), RESOLVED+VERIFIED. 0 open.
No architectural drift introduced; no new invariants beyond what is already
recorded in fhir4ds/viewdef/AGENTS.md.

Recommended Fix Order: none pending. Chunk SOF-VD-09 is CLEAN.

Handoff compression: QA probed all mandate items (0..* AND semantics,
false/empty/null/non-boolean exclusion, description retention, %constants
incl. backtick form, complex FHIRPath, root-scope preservation under
forEach, %resource refs, malformed-path rejection, resourceType ordering)
with native/fallback parity; found one shape-strictness divergence (QA-001)
which the Engineer fixed at the parser boundary with 7 regression tests;
all gates green (1216/1216 viewdef pytest, 144/144 ViewDef conformance,
2832/2832 master, md5-matched binaries).
