# Architect Handoff — SOF-VD-10 EXPLORER (iteration 1, 2026-08-23)

## Golden standard (this iteration's scope: parser typed-error boundary)
1. Every invalid ViewDefinition input reaching `parse_view_definition`,
   `ViewDefinition.from_dict`, or `load_view_definition` must surface as a
   typed `ParseError` — never an interpreter-level crash.
2. No silent fallbacks; boundary conversion must not swallow the cause
   (`from exc` chaining preserved).
3. Fixes general to the input class, not the reproducer (any recursion source
   — `_parse_select`, duplicate-name walk, or `json.loads` — is covered by the
   single boundary translation).
4. Pure-Python changes must not require native rebuilds; binary parity repo vs
   site-packages must hold.

## Audit of the QA-001 fix
- `parse_view_definition` wrapper catches `RecursionError` → typed
  `ParseError` with cause chaining; body moved verbatim to
  `_parse_view_definition`. All three entry points inherit the guard via
  delegation. Meets invariants 1–3. Diff footprint minimal; no adjacent
   refactoring.
- Binary md5s unchanged and matched repo==site-packages
  (fhirpath 57d0634b6ee6eddee9fc06a1355bef5a, cql
  c5b22d58310c1eb7bafa17ce7877f989) — invariant 4 holds (fix is pure
  Python).
- Note: `SQLGenerator.generate` and `to_dict` remain recursive and could
  still raise `RecursionError` for a VD that parses near the limit (e.g.
  depth ~900 where per-frame stack usage differs). Not a violation of the
  parser boundary contract; logged as observation only — the parser now
  rejects depths the interpreter cannot reliably process downstream, and
  the practical window is narrow. No action this chunk.

## QA quality gate (EXPLORER)
Sufficient — no veto. QA probed all mandated boundaries (deep nesting,
10k fan-out, 62 reserved words executed end-to-end, entry-point consistency,
binding case/whitespace strictness, tag/constant meta-collisions, type
confusion at every string field, maximal round-trip, end-to-end execution),
verified claims against the canonical v2 SD, official validate.js, and
decoded official Binary examples, and correctly retracted its own
mis-expectations (resourceType canonical URL, valueDecimal-as-string,
'_x' sql-name) instead of logging false positives.

## Issues
0 CRITICAL / 0 HIGH / 0 MEDIUM open. QA-001 MEDIUM RESOLVED (verified:
reproducer + 4 regression tests + 2832/2832 gate). QA-002/QA-003 LOW
DEFERRED, QA-004 LOW INTENDED (terminal).

## Recommended fix order
None — no open actionable issues.

## Structural health
Sound. Boundary-perfect fix; conformance 2832/2832; iteration 1 >= min 1
with zero non-terminal CRITICAL/HIGH/MEDIUM → CLEAN exit.
