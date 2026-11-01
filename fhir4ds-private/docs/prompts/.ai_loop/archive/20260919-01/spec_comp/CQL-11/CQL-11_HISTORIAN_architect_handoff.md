# Architect Handoff — CQL-11 HISTORIAN (iteration 1)

Scope: structural audit of this launch's diff (macros/math.py Round/RoundTo,
_operators.py decimal overflow guards, 2 regression tests) plus QA-quality
enforcement.

## Verdict
- No architectural drift introduced. Both fixes mirror established
  invariants: system.-prefixed builtins to avoid macro recursion
  (documented file convention), TRY/TRY_CAST only where the CQL 1.5
  arithmetic header mandates overflow-to-null (not silent fallbacks),
  static folding via exact Decimal evaluation (no fixture-value
  special-casing), translator layering preserved (no SQLRaw/to_sql
  mid-pipeline).
- Dual-engine correctness by construction: the Round fix lives in the
  shared Python macro layer registered on both native and supplement
  paths; the translator fix is engine-agnostic. No C++ rebuild required;
  no native sources touched.
- Pre-existing (out of chunk, not logged): RoundTo's DOUBLE intermediate
  path caps exactness at ~15-16 significant digits — irrelevant at
  implementation scale 8.
- QA Enforcer Gate: PASS, no veto. HISTORIAN ran a spec-walk with online
  normative-text verification (cql.hl7.org Appendix B) plus official
  cql-tests fixture cross-checks, probed both engines, re-verified the
  SKEPTIC fixes at new extremes (INT_MIN div -1, -2.5 rounding ties,
  Power corners), and correctly reclassified four apparent divergences
  as INTENDED with spec citations.

## Evidence
- Probe: .temp/qa/cql11_historian2_probe.py (clean on both engines).
- test_arithmetic_part2_parity.py 15/15; CQL pytest 5745 passed / 9
  skipped; full conformance 2832/2832 (ViewDef 144, FHIRPath 935,
  CQL 1706, DQM 47) — baseline holds.

## Compression
QA found 2 HIGH spec violations (Round macro Integer-narrowing corruption;
Decimal overflow raising instead of nulling). Engineer fixed both at root
cause in fhir4ds/cql/duckdb/macros/math.py and
fhir4ds/cql/translator/expressions/_operators.py with focused dual-engine
regression tests; all validation gates green. Issues QA-001/QA-002
RESOLVED, tombstoned in evolution.json, details in ARCHIVE_LOG.md.

## Exit
Zero non-terminal CRITICAL/HIGH/MEDIUM issues; iteration 1 >= min 1.
Clean exit: workflow=null, exit_reason=CLEAN.
