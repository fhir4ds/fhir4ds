# Architect Handoff — FP-20 SKEPTIC (iteration 1, 2026-08-18)

## Golden-standard invariants audited (FP-20 scope)
1. Spec text outranks docstrings; docstrings must not contradict spec
   semantics (violated by context.py %context claims — fixed).
2. Dual-engine lockstep for every FHIRPath semantic surface.
3. Environment variables are a host-extension point; the engine predefines
   only spec-mandated vars and host-supplied extras live at the host layer.
4. Fixture coverage determines intended-gap classification (§10 metamodel).

## Audit findings
- Seam soundness: nested %context resolution delegates to the in-repo engine
  (correct boundary); the DuckDB hand-rolled context layer only feeds
  focus/variable helpers. The docstring seam is now documented.
- Architecture drift (logged as QA-005, DEFERRED): native `fn_isType` uses
  hardcoded field-name→type heuristics (name→HumanName, address→Address,
  identifier, telecom, coding, code, reference, contentType, BackboneElement
  fallback) while the Python fallback uses value-shape structural inference
  (`TypeInfo.create_by_value_in_namespace`: coding→CodeableConcept,
  system+code→Coding, value+unit/code→Quantity, low/high→Range, start/end→
  Period, reference→Reference, contentType→Attachment). Two divergent
  heuristic strategies for the same §6.3/§10 seam — also a partial violation
  of the model-data-driven rule. Must be unified in the FP-20 milestone-review
  drift reconciliation chunk.
- No new hardcoding, silent fallbacks, or test-driven hacks introduced by
  this launch (changes: docstrings, probe fix, new focused parity tests).

## QA Enforcer Gate
QA was thorough: 69 fresh probe cases across three surfaces, spec text
fetched and paraphrased (2018Sep §9-§12), official fixtures cross-checked,
legacy chunk-scoped parity files re-run (which surfaced the drift instances),
grammar diffed against official productions. RETRY_QA = false.

## Exit
Zero non-terminal CRITICAL/HIGH/MEDIUM issues (QA-005 is terminal DEFERRED
to the scheduled milestone-review drift investigation). iteration 1 >=
min_iterations 1. Clean exit. State finalized in evolution.json.
Knowledge transfer done: AGENTS.md FP-20 section + GLOBAL_KNOWLEDGE.md
(Evolution Statistics row, Personality Effectiveness entry).
