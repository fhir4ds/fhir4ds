# Architect Handoff — SOF-VD-05 (iteration 1, 2026-08-23)

## Golden Standard
`.temp/architect/golden_standard_sof_vd05.md` — 8 invariants grounded in the
fresh releases-branch SD 2.0.0, main SD 3.0.0-ballot, functional-model.md, and
the official sof-js validator schema.

## Audit result
Structurally sound for this chunk. The single fix (parser strictness for
select-level unknown fields and present-empty column/select arrays) lands at
the correct boundary: `_parse_select` is the shared choke point consumed by
`parse_view_definition()` and `ViewDefinition.from_dict()`; direct dataclass
construction cannot carry unknown JSON fields or "present-empty" arrays (empty
list is the absent default on dataclasses), so no serializer/generator guard
extension is required — consistent with the SOF-VD-08 empty-unionAll precedent.
No abstraction violations, no hardcoded fixture logic, no silent fallbacks
introduced (the fix REMOVES two silent-drop paths).

Notable spec facts established this launch (recorded in AGENTS.md):
- `select.select` is the SD contentReference recursion mechanism; there is NO
  user-facing contentReference field in any v2 SD — the launch mandate's
  "contentReference changes context without new rows" framing is FHIR-SD
  terminology and must not be implemented.
- `where` is root-only in SD 2.0.0/3.0.0-ballot and absent from the official
  validator's select schema; fhir4ds's select-level where support is a tested
  superset (SOF-VD-09 doctrine), retained in the known-field allowlist.

## QA Enforcer Gate
QA (SKEPTIC) was thorough: 17 falsifiable behavioral hypotheses + 2 native/
fallback parity checks, fresh spec fetches rather than memory, and expectation
errors were self-corrected against spec before logging. No RETRY_QA.

## Issue summary
3 issues: 2 SPEC_VIOLATION MEDIUM (QA-001, QA-002 — both RESOLVED with focused
regression tests), 1 LOW observation (QA-003 INTENDED). Zero non-terminal
CRITICAL/HIGH/MEDIUM issues remain.

## Validation (FINAL tree)
ViewDef pytest 1185/1185; conformance 144/144 ViewDefinition; master gate
2832/2832 (FHIRPath 935/935, CQL 1706/1706, DQM 47/47). Binary md5s recorded
in engineer_handoff.md; no native code touched this launch.

## Recommended Fix Order
None — nothing open. Clean exit at min_iterations=1.
