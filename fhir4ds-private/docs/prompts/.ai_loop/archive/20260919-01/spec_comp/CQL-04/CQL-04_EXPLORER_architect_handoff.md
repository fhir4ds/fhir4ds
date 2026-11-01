# Architect Handoff — CQL-04 EXPLORER (iteration 1, 2026-08-20)

Scope: structural audit of this launch's fixes against the chunk
(CQL 1.5 logical operators) and repo invariants (GLOBAL_RULES CQL section,
AGENTS.md translator doctrine).

## Golden-standard invariants checked
1. Parser tiering must mirror the official cql.g4 precedence, verified
   against the grammar itself, not prose recollection. → QA-001 fix now
   empirically anchored (ANTLR-generated parser from HL7/cql v1.5.3 kept
   in .temp/qa/cql04_explorer2_2026_08_20/). PASS.
2. Logical operators are Boolean-only at the translator boundary; no
   DuckDB truthiness. → QA-003 fix routes value-bearing define references
   through `CAST(... AS BOOLEAN)` correlated scalars; EXISTS retained only
   for row-presence boolean CTEs (pinned doctrine) and EXISTS usage. PASS.
3. Translator layering preserved: fixes are AST/strategy-level; no
   SQLRaw/to_sql introduced; no silent fallbacks (CAST fails loudly on
   non-Boolean text; static Boolean validation still gates operands). PASS.
4. Case lowering must preserve first-match semantics. → QA-002 fix folds
   only provably-dead clauses. PASS.
5. Dual-path parity: all fixes are in the shared parser/translator (single
   SQL source for both engine paths); parity asserted in probes and tests. PASS.

## Findings
- No new architectural findings. One LOW observation (no action): the
  hand-written parser still nests membership/`between` inside the
  comparison tier below equality (grammar has inequality tighter than
  equality); behaviorally equivalent for all probed inputs, and full
  re-tiering is not justified this chunk.

## QA Enforcer Gate
QA (EXPLORER) was thorough: grammar-verified spec anchors, dual-path
parity on every probe, boundary conditions from the chunk mandate
(null-driven FHIR operands, nullological compositions, guards, case/tuple
surfaces, aliases, chains, short-circuit equivalence). Notably QA caught a
regression introduced by a prior launch by re-deriving the spec truth from
the grammar itself. No veto. RETRY_QA = false.

## Health summary
3/3 issues RESOLVED and verified (1 parser precedence, 1 case lowering,
1 reference-strategy/3VL). Validation: CQL pytest 5713 passed / 9 env
skips; conformance 2832/2832 — baseline held. Issues tombstoned in
evolution.json; details in ARCHIVE_LOG.md.

## Recommendation
Clean exit at min_iterations=1: zero non-terminal CRITICAL/HIGH/MEDIUM
issues remain. Chunk CQL-04 cumulative state: SKEPTIC (0 fixes, doctrine
pins), HISTORIAN (1 HIGH parser fix — direction later corrected by this
launch), EXPLORER (3 HIGH fixes).
