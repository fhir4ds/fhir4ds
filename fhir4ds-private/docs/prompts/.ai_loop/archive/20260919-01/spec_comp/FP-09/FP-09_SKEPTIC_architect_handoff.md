# Architect Handoff — FP-09 (iteration 1, 2026-08-17)

## Structural audit of this launch's diff (+83 lines, 3 files)
- `index_of()` reuses the shared `_get_singleton_string` guard (type +
  singleton errors identical to siblings), `FHIRPathCollection`
  results, and the `STRING_FUNCTIONS` registry — no layering violation,
  no silent fallback, additive/backwards-compatible. Consistent with the
  FP-09 HISTORIAN direct-helper doctrine and the UTF-8-aware position
  mandate (Python str.find is code-point based).
- No hardcoded data, no test-specific hacks, no coupling changes.
- Golden-standard invariants relevant here (dual-engine lockstep,
  direct-helper/UDD parity, no toString coercion) all hold.

## QA Enforcer Gate
QA (SKEPTIC) was thorough: 164 dual-path UDF checks (incl. 18 is_valid
forms) + direct-helper probe against live N1 §5.6 text; all five
functions × {spec examples, case sensitivity, emptiness rules,
non-String/multi-item type errors, bounds, UTF-8/emoji/CJK positions,
resource-driven fields, chaining, contains-fn vs contains-operator}.
Initial "failures" were individually re-verified as probe-authoring
errors before dismissal. No RETRY_QA.

## Issue summary (final)
- QA-001 LOW API_COMPLETENESS — RESOLVED (index_of direct helper added;
  validated; conformance 2832/2832 held).
- QA-002 LOW — INTENDED (`''.substring(0)` → {} shared convention).
- QA-003 LOW — INTENDED (negative start/length → {} shared convention,
  consistent with CQL-12 doctrine).

Zero non-terminal CRITICAL/HIGH/MEDIUM issues → CLEAN exit at
iteration 1 (min_iterations=1 met).

## Recommended Fix Order
None pending. Follow-on note for outer orchestrator: direct-helper
module still lacks some §5.6.6+ helpers (upper/lower/replace exist;
toChars exists) — surface is now §5.6.1–§5.6.5 complete.
