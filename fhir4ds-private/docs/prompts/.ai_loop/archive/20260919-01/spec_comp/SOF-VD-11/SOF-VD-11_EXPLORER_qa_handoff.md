# QA Handoff — SOF-VD-11 EXPLORER (2026-08-23)

Personality: EXPLORER (fuzzer/abuser). Chunk: View Runner + IG Examples.
Probes: `/mnt/d/fhir4ds/.temp/qa/sof_vd11_explorer/` (probe1/2/3).

## Probed (all end-to-end parse+generate+DuckDB execute, native AND forced fallback)
- Volume: 1200 patients, mixed multi-value name/address arrays (absent, empty, 1-3 values,
  multi-line streets) through PatientAddresses (1635 rows) and PatientDemographics
  (1028 rows) — exact rowcounts under the forEach doctrine (absent/empty path drops rows;
  forEachOrNull preserves). ~0.05 s each — no performance cliff.
- Unicode/emoji ("Örebro 🏙️") survives the full pipeline intact in both engines.
- UsCoreBloodPressures: 50 patients x 3 encounters x 2 components = 150 rows exact,
  systolic>diastolic pairing verified, native==fallback row-for-row.
- Column extremes: typed decimal accepts 17- and 38-digit integers and 0.1 (DOUBLE
  coercion per pinned doctrine; a 38-digit STRING in a decimal column is correctly
  rejected by the runtime guard). 500-deep chained extensions through a typed Extension
  column. 10,000-element collection column (string[]) returns all 10k.
- Arrow-registered and DataFrame-registered input tables both execute VDs correctly.
- Consumption: fetchall / fetchdf / arrow identical rows and cell-for-cell values.
- Concurrency: 4 parallel DuckDB sessions executing the same VD — identical results,
  no session pollution.
- NULL vs JSON-null vs absent: all three produce NULL in output for absent-value paths
  (both engines agree).

## Issues found
- QA-001 (MEDIUM, FIXED): Python-fallback `fhirpath_scalar` silently returned [] for
  deeply nested (>=128-level) results because `orjson.dumps` raises
  TypeError("Recursion limit reached") at ~127 nesting levels and the row-resilient
  `except TypeError` swallowed it. Native C++ returned the full JSON — dual-engine
  divergence. Fix: `_json_serialize` now falls back to the existing
  `_json_serialize_iterative`. Regression:
  `fhir4ds/fhirpath/duckdb/tests/integration/test_deep_json_serialization_parity.py` (2 tests).
- QA-002 (MEDIUM, FIXED): `conformance/scripts/run_all.py` DQM child intermittently
  crashed at `import argparse` with FileNotFoundError from FileFinder — root cause is
  the WSL/drvfs cwd becoming momentarily unreadable under heavy suite IO, which breaks
  the child's relative script-dir path (os.getcwd() itself was observed failing in the
  parent). Fix: resolve absolute script paths up front + one retry on the transient
  child failure (REV-009 retry doctrine). Verified: 2 clean master runs, DQM log entry
  now present each time.

## NOT A BUG registry additions
- forEach on absent/empty path drops the resource's rows (spec Process(S,N) doctrine);
  my initial volume expectations assumed row preservation — forEachOrNull is the
  preserving variant (already pinned by prior launches).
- `type: "json"` is not a valid column type; complex results need a real FHIR type
  (e.g. Extension) or an untyped primitive path. Typed decimal precision loss beyond
  DOUBLE is the pinned fixture doctrine.
