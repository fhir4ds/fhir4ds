# Engineer Handoff — SOF-VD-01 (2026-08-23, iteration 1)

## Triage
| Issue | Category | Verdict |
|---|---|---|
| QA-001 fhirVersion binding stale code set | SPEC_VIOLATION | CONFIRMED → RESOLVED |

## QA-001 fix (root cause, minimal footprint)
- **Root cause**: `fhir4ds/viewdef/metadata.py:FHIR_VERSION_CODES` held a
  stale R4B-era 42-code set (three-segment versions + milestone codes). The
  SQL-on-FHIR IG (3.0.0-ballot, sushi-config `fhirVersion: 6.0.0-ballot5`)
  binds `ViewDefinition.fhirVersion` REQUIRED to
  `http://hl7.org/fhir/ValueSet/FHIR-version`, whose R6 code system contains
  only 24 two-segment `[publication].[major]` codes.
- **Fix**: replaced the set with the 24 official codes (metadata.py comment
  cites source). Single choke point; parser/types/generator all consume it.
- **Tests**: updated stale expectations `4.0.1/5.0.0 → 4.0/5.0` in
  `test_parser.py`, `test_generator.py`, `test_duckdb.py`; added
  `test_fhir_version_accepts_official_two_segment_codes` + 8-case
  parametrized out-of-binding rejection in `test_parser.py`.
- **Behavior change (intentional, spec-mandated)**: three-segment and
  milestone codes (`4.0.1`, `5.0.0-snapshot1`, `6.0.0-ballot4`, ...) are now
  REJECTED per the required binding; two-segment codes now accepted.

## Validation (fresh, final tree)
- Reproducer probe: 39/39 PASS (`.temp/qa/sof_vd01_skeptic_2026_08_23/probe.py`)
- ViewDef pytest: 1127/1127 (was 1118; +9 new regression tests)
- Conformance: ViewDefinition 144/144, master gate 2832/2832 (FHIRPath 935,
  CQL 1706, DQM 47) — baseline holds.
- Extension binaries untouched (no C++ change); md5s match repo ↔
  site-packages: cql c5b22d58..., fhirpath 57d0634b...

## Files changed
- `fhir4ds/viewdef/metadata.py` (FHIR_VERSION_CODES)
- `fhir4ds/viewdef/tests/unit/test_parser.py` (updates + new tests)
- `fhir4ds/viewdef/tests/unit/test_generator.py` (stale-code updates)
- `fhir4ds/viewdef/tests/integration/test_duckdb.py` (stale-code update)

No new issues discovered during remediation.
