# QA Handoff — FP-14 EXPLORER (§6.2)

## Verdict: 31/32 fresh fuzz cases; 1 REAL parity divergence -> FP-14-F01 (findings-only, OPEN)

**FP-14-F01 (LOW/MEDIUM, findings-only, OPEN):** non-date-shaped string vs resource temporal FIELD
ordering diverges native vs fallback. `birthDate < 'a'` -> native ['true'] (lexicographic coercion
of the FHIR primitive field), fallback [] (strict §6.2 same-type rule; core raises 'Type of
"1974-12-25" (FP_Date) did not match type of "a" (str). InequalityExpression'). Date-SHAPED
strings coerce identically in both engines (pinned JSON-convenience convention, standing test
passes 1/1 in this worktree); @literal System Date vs string is strict-empty on BOTH. Only the
resource-FIELD vs arbitrary-string corner diverges and is UNPINNED. Fallback is the spec-aligned
side; native's lexicographic fallback risks wrong-ordering on malformed data. Fix requires
native rebuild + parity pin — human decision (maintenance worktree is findings-only).

Chains, iif/where compositions, pathological magnitudes, unicode/emoji, quantity edges,
temporal extremes, error containment, 10 seeded randoms (seed 20261002) — all else 0 diffs.

Evidence: .temp/qa/speccomp2/fp14_explorer_probe1.py + re-verification matrix (4 rows).
