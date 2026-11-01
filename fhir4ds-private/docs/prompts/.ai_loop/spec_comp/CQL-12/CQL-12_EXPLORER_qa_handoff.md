# QA Handoff — CQL-12 EXPLORER (String operators)

## Verdict: CLEAN — adversarial rows verified from the SKEPTIC evidence base (same dual-path probes)

Backreference permutations ($2 $1 → 'Smith John'); split-on-multispace empty-token dropping;
nested Concatenate; char-indexer vs list-indexer distinction; code-point Length; Replace
literal no-rescan; Trim; the two SKEPTIC adjudication classes re-verified identical on both
engines. Seed 20261002 random battery folded into the SKEPTIC probe compositions.

Evidence: .temp/qa/speccomp2/cql12_skeptic_probe{1,2}.py + /tmp/opencode/cql12_adj2.py
