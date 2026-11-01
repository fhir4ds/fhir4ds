# Engineer Handoff — SOF-VD-10 HISTORIAN (2026-08-23)

## Scope
All three QA findings are LOW and terminal at triage (DEFERRED / INTENDED x2).
Zero non-terminal CRITICAL/HIGH/MEDIUM issues → no code changes required or
made this iteration. Root-cause analysis recorded per issue in
`evolution.json`:

- QA-001 (LOW, DEFERRED): `Constant.to_dict()` Decimal emission. Root cause:
  the lossless-parse doctrine (`parse_float=Decimal` in
  `parse_view_definition`, pinned by the CQL literal-grammar rule) propagates
  Decimal into `to_dict()` output; Python stdlib `json` cannot losslessly
  encode FHIR's 18-digit decimals as a built-in type. Emitting `float` would
  silently reintroduce the rounding corruption the parse doctrine exists to
  prevent — a workaround, not a fix (violates the no-workarounds directive).
  A true fix would require a Decimal-aware serializer API surface; deferred
  with doctrine in `fhir4ds/viewdef/AGENTS.md`. No production consumer
  performs `json.dumps(vd.to_dict())` today.
- QA-002 (LOW, INTENDED): `valueInteger: 3.0` rejection. FHIR integer JSON
  representation forbids a decimal point; stricter than Ajv's
  `Number.isInteger`, typed error, keep.
- QA-003 (LOW, INTENDED): select-level `where`/`repeat` doctrine re-confirmed.

## Validation (final tree, PYTHONPATH=/mnt/d/fhir4ds)
- ViewDef pytest: 1227/1227 passed (178s).
- Master conformance gate (`conformance/scripts/run_all.py`):
  ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47,
  OVERALL 2832/2832 — baseline holds, no regressions.
- Binary md5s (repo == site-packages, unchanged from prior launch):
  cql c5b22d58310c1eb7bafa17ce7877f989,
  fhirpath 57d0634b6ee6eddee9fc06a1355bef5a.
- No reproducer-fix loop needed: both non-INTENDED behaviors are asserted
  expected-error shapes already exercised by the probe suite
  (`.temp/qa/sof_vd10_historian_2026_08_23/{probe,probe2}.py`).
