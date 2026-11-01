# Architect Handoff — FP-15 EXPLORER (2026-08-18)

## Golden Standard check (scoped to this launch)
- Dual-engine lockstep: HOLDS. All three fixes landed in both engines (or, for
  the parser fix, only native needed change because fallback was already
  correct). Parity re-verified post-redeploy through a fresh connection.
- Data-driven model knowledge: metadata fixes are data entries (JSON + curated
  maps), not resource-specific runtime branches. Suffix keys chosen precisely
  to mirror native name-only semantics instead of diverging.
- No test hacks, no fixture-specific branches; the parser fix is the general
  grammar rule (left-recursion -> loop), not case patching.

## Findings
- ARCH-003 (new, bounded): hand-rolled recursive-descent parser
  (extensions/fhirpath/src/fhirpath/parser.cpp) can silently FLATTEN
  left-recursive ANTLR grammar rules into single-shot conditionals. QA-001 was
  an instance (typeExpression). A systematic pass comparing parser.cpp
  productions against FHIRPath.g4 left-recursive rules is warranted next time
  parser.cpp is touched.
- ARCH-002 (unchanged, open): three curated field-type tables still exist;
  this launch added entries to all three per doctrine. QA-004 (per-path types
  unreachable) is the concrete user-visible cost of not consolidating.

## QA Enforcer Gate
EXPLORER QA was NOT lazy: 121-case probe covering every chunk-mandated angle
(all primitives on real fields, chains, where/select/repeat/iif feeding,
namespace spellings, quantity subtypes, multi-type contained, multi-item
focuses, deep nesting, both syntactic forms) plus 2 isolation drills, dual-path
throughout. No RETRY_QA.

## State
Iteration 1 >= min_iterations 1; zero non-terminal CRITICAL/HIGH/MEDIUM issues
(QA-004 LOW DEFERRED is terminal). Clean exit.
