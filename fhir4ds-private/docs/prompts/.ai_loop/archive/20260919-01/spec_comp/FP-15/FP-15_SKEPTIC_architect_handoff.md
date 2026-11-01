# Architect Handoff — FP-15 fresh SKEPTIC launch (2026-08-18), iteration 1

## Structural health of this launch's diff
All 5 fixes are surgical, spec-grounded, and general (class-level, not
case-level). Dual-engine lockstep was honored: QA-002 landed in evaluator.cpp
with rebuild+redeploy; QA-001/003/004/005 were Python-surface-only where native
was already correct. Golden standard for this audit in
`/mnt/d/fhir4ds/.temp/architect/golden_standard.md`.

Issues by category this iteration: SPEC_VIOLATION 3 (all RESOLVED),
PARITY 2 (RESOLVED), KNOWN_LIMITATION 1 (INTENDED). Zero open issues.

## Architectural findings (logged, not fixed — pre-existing drift)
- **ARCH-001 (LOW, drift):** udf.py choice-assertion rescues
  (`_resolve_choice_type_assertion_any`) can still OVERRIDE correct non-empty
  engine results for genuine choice fields if their regex/table is ever wrong
  again (QA-003 was an instance). Long-term: rescues should only fire on empty
  engine results, or be deleted once the engine covers choice resolution.
- **ARCH-002 (LOW, REV-002 widening):** the QA-001 fix adds another
  hand-maintained hierarchy override site (nodes.py explicit uri/Money/Dosage/
  Timing overrides) beside fhir_model.py's merge and the native tables —
  same drift family as REV-002; generate from models/r4 when next touched.
- **ARCH-003 (LOW):** typecheck.py now hand-duplicates the distinct System
  type-name list (native `isDistinctSystemTypeName`) — keep both lists in
  lockstep when a new System type is added.

## QA Enforcer Gate
QA was NOT lazy: 121 fixture-anchored dual-path cases covering both syntax
forms, System vs FHIR namespaces, subtype chains, choice `as` navigation,
empty/null focus, multi-item, backtick/qualified spellings, plus the exported
helper surface and is_valid classification. Root causes were diagnosed before
filing. RETRY_QA = false.

## Recommended Fix Order (future iterations)
1. ARCH-001 rescue-override semantics (guard on empty engine result).
2. ARCH-002/003 metadata duplication (build-time generation, REV-002 family).

## State
Iteration 1 ≥ min_iterations; zero non-terminal CRITICAL/HIGH/MEDIUM issues →
CLEAN EXIT recommended.
