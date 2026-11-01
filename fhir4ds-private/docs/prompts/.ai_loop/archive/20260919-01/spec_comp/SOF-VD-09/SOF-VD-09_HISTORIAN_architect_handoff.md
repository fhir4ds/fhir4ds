# Architect Handoff — SOF-VD-09 HISTORIAN (2026-08-23, iteration 1)

Golden Standard: `.temp/architect/golden_standard_sof_vd09_historian.md`
(8 invariants: Process(S,N) focus semantics, single builtin-variable registry,
no silent misrouting, symmetric fail-loud guards, dual-engine parity,
strict-parser/permissive-dataclass split, AST-based expression analysis,
no test hacks).

## Audit verdict
QA-001 (HIGH) fix is structurally sound and invariant-conformant:
- Symmetry restored (invariant 4): the "mixes built-in ViewDefinition
  contexts" fail-loud contract no longer depends on expression token order.
- AST-based analysis (invariant 7): `_prefix_tail_has_focus_operand` walks the
  shared `parse_fhirpath` AST spine; no regex/string heuristics.
- No silent fallback (invariant 3): previously silent wrong-input evaluation
  now raises typed ValidationError.
- Dual parity (invariant 5): guard is generator-level; 6 execution cases
  asserted identical on native and forced fallback.
- Minimal footprint: only `generator.py` context routing + new test class;
  strict/permissive parser split untouched; no new builtins.

Residual risks (LOW, logged, not blockers):
- Indexer (`[...]`) arguments under a `%rootResource.` prefix are treated as
  focus-rooted operands by the spine walk and will fail loud; correct-input
  lowering of indexers is genuinely ambiguous on the single-input UDF surface,
  so fail-loud is the doctrinally safe default.
- Function arguments (lambda `$this` scope) are deliberately NOT guarded —
  they evaluate against the routed input, matching pre-fix behavior and
  `where()` semantics; documented in the helper docstring.

QA Enforcer Gate: QA was thorough — full chunk mandate (root where semantics,
parser shape, fixtures, both engines, new-divergence hunting beyond SKEPTIC's
fixed surface). Found a NEW HIGH silent-data bug. No veto; RETRY_QA false.

## Validation (final tree, PYTHONPATH=/mnt/d/fhir4ds)
- viewdef pytest 1227/1227; QA probe 25/25 native+fallback
- ViewDefinition conformance 144/144 (where.json 8/8)
- Master gate: ViewDef 144, FHIRPath 935, CQL 1706, DQM 47 → 2832/2832 (baseline holds)
- fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a identical
  repo bundle == ~/.local site-packages (no native changes)

## Handoff compression
QA (HISTORIAN) re-verified the full root-where mandate and hunted new scope/
ordering corners; 23/25 probe assertions conformant, exposing QA-001: a
`%rootResource.`/`%resource.`-prefixed expression whose binary-operator
operands reference the current focus was silently evaluated against the ROOT
JSON inside iterators (both engines) — the existing mixed-context guard was
order-dependent. Engineer fixed it with an AST spine walk
(`_prefix_tail_has_focus_operand` + shared `_ast_uses_current_focus`) raising
the same typed ValidationError in both orderings; continuations, function
args, and literal operands unaffected; 11 parametrized regression tests with
native==fallback parity. All gates at baseline. Iteration 1 = min_iterations
with zero non-terminal CRITICAL/HIGH/MEDIUM issues → CLEAN exit.
