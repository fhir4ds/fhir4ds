# FP-16 QA Handoff (HISTORIAN, iteration 1, 2026-08-18)

Chunk: FHIRPath §6.4 Collections — `|` (union), `in` (membership), `contains` (containership).

Method: HISTORIAN personality. Re-verified SKEPTIC's fix surface and hunted NEW divergences
with a fresh 30-case dual-path probe (native C++ extension vs forced Python fallback) plus
8-case exported-helper-API audit, at `/mnt/d/fhir4ds/.temp/qa/fp16_historian_probe.py`.
Normative text verified directly against hl7.org/fhirpath/N1 §6.4, §5.4.1 (union fn), §6.1.1
(precision equality), §5.1.8/5.1.9 (subsetOf/supersetOf membership semantics).

New angles beyond SKEPTIC's 37 cases:
- §5.4.1 `union()` FUNCTION form (spec: synonymous with `|`): dedup across both operands,
  empty-input/empty-arg, Integer=Decimal dedup, deep-object dedup — all correct on both paths.
- Precision-mismatch equality inside dedup/membership: `(@2012-01 | @2012)` not deduped (2),
  `@2012-01 in (@2012|@2013)` → false (empty equality not True) — spec-correct both paths.
- Singleton right operand of `in` / left of `contains` (`1 in 1`, `1 contains 1`) → true.
- Calendar vs definite duration quantities: `(1 year | 1 'a')` → 2 (not equal per §6.1.1);
  `(1 second | 1 's')` → 1 (equal per spec) — correct both paths.
- Membership inside iteration ($this in where/select), grammar edges (no-space `1|2`, `1 in(1|2)`).
- subsetOf/supersetOf (§5.1.8/9, `=`-membership consumers): both correct; supersetOf over a
  collection with duplicates correctly returns true (membership, not multiset equality).
- Exported helper API `operators.union/membership/contains`: all 8 checks OK — SKEPTIC's
  QA-001 fix (multi-item singleton errors) holds and union() helper uses `=` semantics.

Findings: ZERO new issues. 0 parity mismatches, 0 spec deviations, 0 expectation failures
(after correcting one wrong probe expectation of mine on supersetOf).

Regression check: full conformance baseline 2832/2832 (ViewDef 144, FHIRPath 935 — including
official testUnion/testIn/testContainsCollection fixture groups —, CQL 1706, DQM 47).

Verdict: chunk FP-16 is spec-compliant on both evaluation paths. Clean exit recommended.
