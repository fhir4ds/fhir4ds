# Engineer Handoff — SOF-VD-11 EXPLORER (2026-08-23)

## QA-001 (MEDIUM) — fixed
- Reproducer: `fhirpath_scalar(<300-deep chained extensions>, 'extension')` -> [] with
  WARNING "Recursion limit reached"; native returned full JSON. orjson.dumps ceiling
  measured at ~127 nesting levels (TypeError).
- Root cause: `fhir4ds/fhirpath/duckdb/udf.py::_json_serialize` used orjson only; the
  TypeError landed in fhirpath_scalar's broad `except (ValueError, TypeError, ...)`
  row-resilience handler and was swallowed to empty — a silent native/fallback
  divergence.
- Fix: `_json_serialize` catches the orjson recursion TypeError and falls back to the
  pre-existing `_json_serialize_iterative` (explicit stack, already used by repeat
  traversal). No new abstraction; Decimal/None/bool leaves handled by the existing
  `_json_scalar_serialize`.
- Regression: `fhir4ds/fhirpath/duckdb/tests/integration/test_deep_json_serialization_parity.py`
  (unit serializer round-trip + native==fallback parity on 300-deep resource). 2/2 pass.
- Python-only change; extension binaries untouched (md5 unchanged, see architect handoff).

## QA-002 (MEDIUM) — fixed
- Reproducer: `python3 conformance/scripts/run_all.py` intermittently printed
  "Error: DQM (QI Core 2025) suite failed with exit code 1" while the summary still
  showed 47/47 from a stale report (fresh dqm_report.json NOT written; no DQM log_run
  entry). Child died at `import argparse` — FileNotFoundError from FileFinder on the
  relative dir 'conformance/scripts'; separately observed `os.getcwd()` itself raise
  FileNotFoundError in the parent under heavy suite IO (WSL/drvfs flake).
- Fix in `conformance/scripts/run_all.py`: resolve each suite script to an absolute
  path before spawning (fallback resolution via `__file__` if cwd is unreadable), and
  retry a child that died with the transient rc=1 once before declaring failure.
- Verified: two consecutive clean master runs (rc=0, DQM conformance.log entry written
  each time, 2832/2832).

## Gates (final tree, PYTHONPATH=/mnt/d/fhir4ds)
- ViewDef pytest: 1231 passed. Conformance: ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47, OVERALL 2832/2832.
- Extension md5 (repo == site-packages, unchanged this launch): fhirpath
  57d0634b6ee6eddee9fc06a1355bef5a, cql c5b22d58310c1eb7bafa17ce7877f989.
