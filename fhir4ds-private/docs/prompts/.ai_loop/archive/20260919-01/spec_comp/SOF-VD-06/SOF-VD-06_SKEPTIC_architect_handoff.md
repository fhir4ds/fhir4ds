# Architect Handoff — SOF-VD-06 (forEach/forEachOrNull), iter 1

## Golden Standard
.temp/architect/golden_standard.md (10 invariants, grounded in the canonical v2 Process(S,N) formal semantics fetched from FHIR/sql-on-fhir-v2 main and the sql-on-fhir.js reference implementation).

## Audit result
Structurally clean for this chunk. Generator implements forEach via CROSS JOIN LATERAL and forEachOrNull via LEFT JOIN LATERAL with null_preserve_var threading (Process step 3); no hardcoded resource-type branches, no TODO/FIXME debt in generator/unnest/parser. All 10 invariants verified empirically (see qa_handoff).

## QA Enforcer Gate
QA was NOT lazy: it probed parser validation (combo rejection, non-string/whitespace iterators, invalid FHIRPath), row multiplication incl. singleton/primitive/boolean/contained foci, null-row preservation depth (parent columns, collection columns, nested forEach/repeat inside forEachOrNull), %rowIndex (0-based, per-level, top-level, null-row, sibling independence), %context/%resource/%rootResource in iterated contexts, where+forEach interplay, fixture freshness vs upstream (byte-identical), and pinned verdicts to the normative Process(S,N) text. RETRY_QA not set.

## Compressed handoff
Zero CRITICAL/HIGH/MEDIUM. Two LOW observations terminal as DOCUMENTED (QA-001 duplicate forEach JSON keys = JSON last-wins, reference-identical; QA-002 select.where+forEach per-focus evaluation, doctrine pinned in viewdef/AGENTS.md since v2 removed Select.where). No code changes this launch.

## Validation (final tree, PYTHONPATH=/mnt/d/fhir4ds)
- pytest fhir4ds/viewdef: 1185 passed.
- run_viewdef.py: 144/144.
- run_all.py master gate: OVERALL 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47), single pass, no retry needed.
- Binary md5s match repo bundle vs site-packages: cql c5b22d58310c1eb7bafa17ce7877f989; fhirpath 57d0634b6ee6eddee9fc06a1355bef5a. (No native changes this launch.)

## Recommended fix order
None — no open issues. Clean exit at min_iterations=1.
