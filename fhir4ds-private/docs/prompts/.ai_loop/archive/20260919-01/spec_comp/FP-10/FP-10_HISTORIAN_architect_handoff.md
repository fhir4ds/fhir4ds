# Architect Handoff — FP-10 HISTORIAN (iteration 1, CLEAN exit)

## Structural audit summary

Golden-standard invariants applied (dual-engine lockstep, no silent
fallbacks, helper/engine contract parity, dialect divergences must be
spec-sanctioned AND example-independent, rebuild+redeploy after native
edits):

- The central finding is architectural: the SKEPTIC launch had pinned
  "no named groups natively" as a dialect-sanctioned divergence, but the
  spec's own §5.6.10 canonical example depends on `(?<name>…)`/`${name}`.
  Invariant sharpened: a dialect limitation is only spec-sanctioned when
  the spec's own normative examples do not depend on the feature. Recorded
  in AGENTS.md and GLOBAL_KNOWLEDGE.md (doctrine supersedes the old pin).
- Lockstep audit of the fix: the named-group translation now lives in all
  four coupled surfaces (native normalize, Python engine matches(),
  direct helper matches(), udf is_valid regex precheck). The precheck gap
  (is_valid=False for valid §5.6.10 syntax) is exactly the
  error-message-contract coupling family from GLOBAL_RULES — regex-literal
  validation must compile through the same translation as evaluation.
- No silent fallbacks introduced: `${unknown}`/`$word`/`${N}` pass through
  as literals in both engines by construction (only existing named groups
  are rewritten), so no behavior is masked.
- QA ENFORCER GATE: QA was NOT lazy — 107 fresh dual-path cases with new
  angles (overlapping replace scan, empty-string regex, two-digit/dangling
  dollar substitutions, toChars chaining, titlecase case-mapping),
  re-verified all 5 prior fixes, and correctly isolated a probe artifact
  (regex-level \u) before filing. RETRY_QA not warranted.

## Validation (Recovery Gate)

- Probe: 107 dual-path cases → 3 diffs, all pinned dialect divergences.
- String suites: 141/141 passed.
- Full fhir4ds/fhirpath pytest tree: 1774/1774 passed.
- Full conformance: ViewDefinition 144/144, FHIRPath 935/935, CQL
  1706/1706, DQM 47/47 — OVERALL 2832/2832 (baseline held).

## State

Issues terminal: QA-001 HIGH → RESOLVED+verified (iter 1); QA-002 MEDIUM →
RESOLVED+verified (iter 1); QA-003 LOW → DEFERRED (dialect, pinned).
Zero non-terminal CRITICAL/HIGH/MEDIUM issues; iteration 1 ≥ min 1 → CLEAN
exit, workflow=null.

## Institutional memory updates

- AGENTS.md: FP-10 HISTORIAN section (named-group 4-surface lockstep rule,
  superseded doctrine, helper-family 6th instance, C++ single-char-name
  gotcha, verified-clean list).
- GLOBAL_KNOWLEDGE.md: Evolution Statistics row FP-10-2; HISTORIAN
  personality effectiveness entry.
