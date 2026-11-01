# Architect Handoff — SOF-VD-02 (SKEPTIC), iteration 1

## Golden-standard invariants audited (viewdef constants surface)
1. Built-in FHIRPath variables canonically in `constants.py:FHIRPATH_BUILTIN_VARIABLES` — holds; fix introduced no duplicate set.
2. Constant value/name validation metadata centralized in `types.py`; the new integer64 range guard lives at the RESOLUTION layer (`constants.py`) — correct boundary: an unreferenced spec-valid integer64 constant remains valid; only substitution into FHIRPath (whose Integer literals are 32-bit) is unrepresentable. No drift.
3. No silent fallbacks: the fix converts a silent-empty into a typed `ConstantResolutionError` (inherits SQLOnFHIRError/ValueError) — exception typing preserved through `SQLGenerator.generate`. Holds (verified end-to-end).
4. Single-writer: my marker present in `constants.py` after edit; no sibling overwrite.
5. Model knowledge data-driven: no hardcoding introduced; guard is generic (range check on class of values).

## QA Enforcer Gate
QA was NOT lazy: ~90 probes across parser boundaries, substitution semantics in every FHIRPath context, lexical guards, engine ground-truth separation (executed substituted literals directly), and full end-to-end execution of both official constant fixtures against expect rows — an axis the committed suite lacks (it only parses fixtures). RETRY_QA not warranted.

## Structural findings
- 0 new architectural issues. 1 fix (QA-001) verified: reproducer raises, regression tests added, gates green.
- Observation (follow-up candidate, not an issue): committed `test_spec_compliance.py` never executes official fixture `expect` rows; QA probe5 (`.temp/qa/sofvd02_skeptic_2026_08/probe5.py`) is the only end-to-end oracle. Recommend promoting fixture execution into the committed suite in a future chunk.

## Handoff compression
QA (SKEPTIC) probed constants end-to-end and found one real divergence: integer64 constants beyond int32 silently evaluate empty in both engines (spec-valid value, engine-unrepresentable literal). Engineer fixed it with a typed error at resolution in `constants.py`, added 6 regression tests, updated one test that had pinned the silent shape. Gates: viewdef pytest 1159/1159, ViewDef conformance 144/144, master 2832/2832, binaries unchanged (fhirpath 57d0634b6ee6eddee9fc06a1355bef5a repo == site-packages). State: issue QA-001 RESOLVED/verified; zero non-terminal CRITICAL/HIGH/MEDIUM; CLEAN exit at iteration 1 (min_iterations=1).
