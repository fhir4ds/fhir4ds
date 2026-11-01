# QA Handoff — FP-02 SKEPTIC (FHIRPath §4.2-§4.5)

## Verdict: CLEAN — zero defects (0 issues logged)

~57 fresh dual-path (native vs forced fallback) cases across 3 batteries:
- probe1 (24): §4.4 empty propagation, §4.5 singleton truthiness, §4.2 typed
  operators, §4.3 invocation forms — 24/24 PASS, zero flags.
- probe2 (17): precedence, type rejections, is_valid quartet, JSON-null —
  15 ok + 2 flags, both adjudicated NOT bugs (below).
- probe3 (16): empty-criterion iif, singleton operators, decimal exactness —
  15 ok + 1 flag, adjudicated NOT bug (below).

## Adjudications (probe-expectation artifacts, NOT engine bugs)
1. `name.given` "flattens" flag = str() display formatting only; values correct.
2. `(1 | 2) = 1` → ['false'] both engines — my 'empty' expectation was WRONG:
   §6.1.1 count-mismatch equality is FALSE; official fixtures testEquality5/6/7
   pin this and were verified GREEN live.
3. `1 / 3 * 3 = 1` → ['false'] both engines — CORRECT: 1/3 is the exact 28-sig
   Decimal 0.333...333; ×3 = 0.999...999 ≠ 1 (byte-identical across engines).
4. Multi-item `nums = 1` → ['false'] (count mismatch) on both engines — consistent
   with the core engine's direct evaluation.

## Evidence
Scripts: .temp/qa/speccomp2/fp02_skeptic_probe{1,2,3}.py
Logs: /tmp/opencode/fp02s{1,2,3}.log
