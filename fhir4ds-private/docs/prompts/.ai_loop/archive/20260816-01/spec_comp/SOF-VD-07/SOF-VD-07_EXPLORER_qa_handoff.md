# QA Handoff — SOF-VD-07 / EXPLORER (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-07 — SQL-on-FHIR ViewDefinition.select.repeat.
**Spec**: https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
(v2.1.0-pre). EXPLORER pathological-input probe of repeat traversal boundaries.
**Personality**: EXPLORER (Fuzzer / Abuser).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-07_EXPLORER/probe.py`
**Result**: **PASS — 8/10 probes passed; 2 informational INTENDED findings (test-harness / hypothesis errors, not bugs); 0 real issues.**

## Pathological Inputs Tested

- **E1** deep nesting 300 levels — initial FAIL (expected 301, got 300).
  Investigated: **test-harness bug** — fixture construction used
  `node['item'][0]` instead of `node`, dropping the top-level `n1`. The
  implementation correctly returned 300 nodes for a 300-deep chain.
  Classified INTENDED (test-harness error).
- **E2** `$this` self-traversal cycle guard — PASS.
- **E3** overlapping repeat paths preserve duplicates — initial FAIL
  (expected 3, got 2). Investigated against the official `repeat.json`
  "item and answer.item" spec_test: that test has 1.1.1 reachable via
  both `item` and `answer.item` paths but expects it to appear only ONCE
  (6 de-duplicated rows, not 7). Confirms **de-duplication is the
  spec-correct behavior**. Classified INTENDED (hypothesis error).
- **E4** repeat over 1000-node flat array — PASS.
- **E5** repeat + nested select — PASS.
- **E6** repeat over unicode linkIds (日本語, 🄰, Sánchez) — PASS.
- **E7** repeat with `where` filter on repeated node — PASS.
- **E8** malformed repeat FHIRPath rejected — PASS.
- **E9** repeat over object-typed answer nodes — PASS.
- **E10** repeat + sibling column Cartesian — PASS.

## Spec Verification

- Functional model (https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/functional-model.html):
  `repeat` is documented separately from `unionAll`. The official
  `repeat.json` "item and answer.item" fixture expects de-duplicated
  node hits when multiple paths visit the same node (6 rows, not 7),
  matching the project's documented "union duplicate node hits across
  paths" behavior (AGENTS.md SOF-VD-07 SKEPTIC 2026-05-20).
- Deep-nesting iterative traversal handles 300+ levels without Python
  recursion limit (SOF-VD-07 EXPLORER 2026-05-20 fix intact).

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-07_EXPLORER/probe.py`

## Notes

- All prior SOF-VD-07 fixes intact. No source changes required.
- ViewDefinition pytest 1055/1055 PASS.
