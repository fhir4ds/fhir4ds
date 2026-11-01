# Architect Handoff — CQL-20 Aggregate Functions (HISTORIAN, iteration 1)

## Structural audit (scoped to this launch's diff)
Golden standard: CQL Translator Invariants in GLOBAL_RULES.md (no SQLRaw/to_sql
mid-pipeline, no silent fallbacks, layered translation, general not hardcoded).

- **Layering**: all fixes live in the translator expression layer
  (`_functions.py`, `_operators.py`); no engine-specific strings beyond the
  existing SQL-cast vocabulary. PASS.
- **Generality**: the new inference (Boolean-result operators, arithmetic
  promotion) is generic; no resource/measure hardcoding. PASS.
- **Silent fallbacks**: none added; QA-002 converts silent binder leaks into
  typed errors. PASS.
- **Drift (existing, not worsened)**: aggregate lowering still has three
  routing surfaces (identifier branches, query branch, generic
  `_wrap_list_aggregate`) — the SKEPTIC LOW-DEFERRED duplication note stands;
  the new numeric dispatch reuses `_translate_list_aggregate_dispatch`, so
  convergence is improving, not regressing.
- **Fragility found during audit**: type-inference widening is a
  high-blast-radius surface — the mid-fix CMS128 DQM regression (46/47)
  proved a two-line inference change can misroute struct-valued elements
  into numeric list_aggregate. Documented as an invariant in
  fhir4ds/cql/AGENTS.md (unknown operands numeric ONLY if plain Identifiers;
  DQM suite mandatory after inference edits).

## QA Enforcer Gate
QA was NOT lazy: 86-case spec-example sweep + 42-case 3-engine dynamic/DQM
shaped probe, re-verified the SKEPTIC's 6 fixes, and hunted new divergences
(found 2 + 1 pre-existing via bisect). RETRY_QA = false.

## State
Compressed record: QA found 2 issues (QA-001 HIGH dynamic aggregate DOUBLE
lowering losing Decimal exactness/Integer typing; QA-002 MEDIUM dynamic
non-numeric operands leaking binder errors). Engineering fixed both at root
cause, discovered and fixed a pre-existing HIGH (QA-004 identifier-arithmetic
INTEGER truncation, `Sum({0.1,0.2}+0.0)`→0), adjudicated QA-003 INTENDED
(CQL-05), and bisect-attributed QA-005 (Ratio accessor, pre-existing,
DEFERRED out-of-chunk). Details archived in ARCHIVE_LOG.md.

## Validation (final tree)
Master gate 2832/2832 — ViewDef 144, FHIRPath 935, CQL 1706, DQM 47/47
(DQM retried per REV-009 after the mid-fix 46/47 regression; final-state
runs green). Focused: aggregate parity 33/33, arithmetic part1+2 29/29,
v2 expressions 147/147, list part1+2 65/65. Binaries unchanged (cql
3e7d4167143e01907fdd8561db43b7d7, fhirpath 57d0634b6ee6eddee9fc06a1355bef5a;
repo bundle == site-packages).

## Recommended Fix Order (next owner)
1. QA-005 Ratio accessor (CQL-03 surface) — small, has a failing test already.
2. Aggregate lowering unification (LOW, carried from SKEPTIC).

## Exit
Zero non-terminal CRITICAL/HIGH/MEDIUM issues; iteration 1 >= min_iterations
1. Exit reason: CLEAN.
