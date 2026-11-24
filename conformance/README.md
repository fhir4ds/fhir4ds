# Spec Conformance

This directory contains scripts and reports for validating `fhir4ds` against official specifications for FHIRPath, CQL, and SQL-on-FHIR ViewDefinitions.

## Structure

- `scripts/`: Implementation-specific runners that execute official test suites.
- `reports/`: Generated JSON reports showing current pass/fail status for each test case.

## Test Suites

### Master Health Check
Runs all conformance suites and displays a unified summary table.
- **Run**: `python3 conformance/scripts/run_all.py`

### SQL-on-FHIR ViewDefinition (v2)
- **Source**: `fhir4ds/viewdef/tests/spec_tests/`
- **Run**: `python3 conformance/scripts/run_viewdef.py`
- **Output**: `conformance/reports/viewdef_report.json`

### FHIRPath (R4)
- **Source**: `fhir4ds/fhirpath/tests/compliance/r4/`
- **Run**: `python3 conformance/scripts/run_fhirpath_r4.py`
- **Output**: `conformance/reports/fhirpath_report.json`

### CQL (Clinical Quality Language)
- **Source**: `fhir4ds/cql/tests/official/cql-tests/tests/cql/` (vendored; pin + counts in `fhir4ds/cql/tests/official/corpus_manifest.json`)
- **Run**: `python3 conformance/scripts/run_cql.py`
- **Output**: `conformance/reports/cql_report.json`
- **Failure mode**: exits **2** when the corpus is absent/empty/incomplete (FHIR4-45); a missing corpus is never reported as a pass.

### DQM (QI Core 2025)
- **Source**: `tests/data/ecqm-content-qicore-2025/`
- **Run**: `python3 conformance/scripts/run_dqm.py`
- **Output**: `conformance/reports/dqm_report.json`

## Goals
The goal of these scripts is to provide a transparent view of spec compliance, documenting known gaps and ensuring that new library features maintain or improve compatibility with official standards.
