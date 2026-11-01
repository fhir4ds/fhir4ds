# Architect Handoff — CQL-14 iteration 1 (EXPLORER)

## Compression
QA (EXPLORER) probed the full timing-phrase qualifier × comparison-family ×
precision matrix, open/closed unbounded bounds, Time-only intervals,
mixed-precision uncertainty, Now()/Today()/TimeOfDay() arithmetic,
tz-carrying and sub-second Subtract, Time() ctor boundaries, boolean chains,
define aliases, and e2e FHIR where-clause execution — dual-engine throughout
(workspace `.temp/qa/cql14_explorer2/`). Two HIGH spec violations found and
fixed by the engineer: (QA-001) `starts/ends same <prec> or after/before`
dropped the relative qualifier at parse (→ same-as equality; no-precision
forms ParseError'd) — parser now follows the CQL grammar production
`same dateTimePrecision? (relativeQualifier|'as')` and the tail dispatch no
longer lets the quantity-offset heuristic shadow the same-family;
(QA-002) `starts/ends on or before/after <prec> of` hardcoded DATE casts,
ignoring the inner `precision of` — now lowers to cqlSameOrBeforeP/
cqlSameOrAfterP at the specified precision. Both fixes are translator-level
(dual-engine by construction, no C++ changes). Fresh validation: part2
parity 9/9, focused temporal/interval parity 79 passed, related unit filter
223 passed, master gate 2832/2832 — baseline held. Golden standard for this
launch: `.temp/architect/golden_standard_cql14_explorer.md`.

## Structural health
- No new invariant violations in the diff: fixes are general (all
  precisions, both qualifiers, points/intervals/mixed), spec-grounded
  (§9.18/§9.19/§9.24/§9.25/§9.26 + reference cql-to-elm semantics), no
  SQLRaw, no silent fallbacks, no fixture-specific branches.
- Architecture drift (logged, MEDIUM, recurring): operator-STRING prefix
  dispatch in `_translate_tail_operators` (`startswith("starts ") and
  " or " in operator`) is a heuristic over rendered operator strings rather
  than structured AST timing phrases; this is the second time in CQL-14's
  history that dispatch ordering silently mis-routed a grammar form (first:
  no-precision same-or; now: same-or-with-qualifier). Recommended long-term
  fix order: (1) represent timing phrases as structured AST nodes
  (qualifier, precision, relativeQualifier, bound selector) instead of
  flattened operator strings; (2) then collapse the three parallel
  dispatch sites (`_translate_tail_operators`, `_translate_same_operator`,
  `_translate_starts_op`/`_translate_ends_op`) into one table keyed by the
  structured form. No action required this launch.

## QA Enforcer Gate
QA was thorough: boundary matrices, both engines, e2e execution, spec
verification against live 2020May spec HTML plus the reference cql-to-elm
translator source. No veto. RETRY_QA remains false.

## Issue counts
SPEC_VIOLATION: 2 (both HIGH, both RESOLVED + verified this iteration).
Architectural drift notes: 1 (string-dispatch fragility, deferred by design).
