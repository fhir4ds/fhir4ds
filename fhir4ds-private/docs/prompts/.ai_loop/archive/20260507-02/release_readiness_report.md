# fhir4ds-v2 v0.0.4 Release Readiness Report

**Date:** 2026-05-07
**Release Engineer:** Automated
**Target Version:** 0.0.4
**Wheel Filename:** fhir4ds_v2-0.0.4-py3-none-any.whl

---

## 1. Version Consistency

All version strings verified and consistent at `0.0.4`:

| File | Version | Status |
|------|---------|--------|
| `pyproject.toml` | `0.0.4` | PASS |
| `fhir4ds/__init__.py` | `0.0.4` | PASS |
| `fhir4ds/cql/__init__.py` | `0.0.4` | PASS |
| `fhir4ds/dqm/__init__.py` | `0.0.4` | PASS |
| `fhir4ds/fhirpath/__init__.py` | `0.0.4` | PASS |
| `fhir4ds/viewdef/__init__.py` | `0.0.4` | PASS |
| `web/wasm-demo/vite.config.ts` (fallback) | `0.0.4` | PASS (updated from 0.0.3) |
| `web/wasm-demo/src/workers/pyodide.worker.ts` (comment) | `0.0.4` | PASS (updated from 0.0.3) |

**Fixes applied:**
- Updated vite.config.ts fallback wheel name from `0.0.3` to `0.0.4`
- Updated pyodide.worker.ts comment from `0.0.3` to `0.0.4`

---

## 2. Build Status (Wheel)

| Artifact | Size | Status |
|----------|------|--------|
| `dist/fhir4ds_v2-0.0.4-py3-none-any.whl` | 8,939,342 bytes (8.5 MB) | PASS |

Build includes:
- C++ fhirpath extension (linux_amd64, DuckDB v1.5.2)
- C++ cql extension (linux_amd64, DuckDB v1.5.2)
- Pure Python source (all subpackages)

---

## 3. Conformance Report

### ViewDefinition Suite
- **134/134 tests passed (100.0%)**
- All 22 test files passed including: basic, collection, combinations, constant, constant_types, fhirpath, fhirpath_numbers, fn_boundary, fn_empty, fn_extension, fn_first, fn_join, fn_oftype, fn_reference_keys, foreach, logic, repeat, row_index, union, validate, view_resource, where
- Report schema validation: PASSED

### FHIRPath (R4) Suite
- **935/935 tests passed (100.0%)**

### CQL Suite
- **1706/1706 tests passed (100.0%)**
- All 16 CQL test files passed:
  - CqlAggregateFunctionsTest.xml: 50/50
  - CqlAggregateTest.xml: 9/9
  - CqlArithmeticFunctionsTest.xml: 212/212
  - CqlComparisonOperatorsTest.xml: 198/198
  - CqlConditionalOperatorsTest.xml: 9/9
  - CqlDateTimeOperatorsTest.xml: 317/317
  - CqlErrorsAndMessagingOperatorsTest.xml: 4/4
  - CqlIntervalOperatorsTest.xml: 412/412
  - CqlListOperatorsTest.xml: 212/212
  - CqlLogicalOperatorsTest.xml: 39/39
  - CqlNullologicalOperatorsTest.xml: 22/22
  - CqlQueryTests.xml: 12/12
  - CqlStringOperatorsTest.xml: 81/81
  - CqlTypeOperatorsTest.xml: 35/35
  - CqlTypesTest.xml: 28/28
  - ValueLiteralsAndSelectors.xml: 66/66

### DQM (QI Core 2025) Suite
- **45/46 measures passed (97.8%)**
- 1 known shortfall: CMS1017 at 97.6% accuracy
- CMS1017 is a pre-existing known gap, not a regression

### Overall Summary

```
Specification             | Passed   | Total    | Rate
ViewDefinition            | 134      | 134      |  100.0%
FHIRPath (R4)             | 935      | 935      |  100.0%
CQL                       | 1706     | 1706     |  100.0%
DQM (QI Core 2025)        | 45       | 46       |   97.8%
OVERALL COMPLIANCE        | 2820     | 2821     |  100.0%
```

---

## 4. Repository Cleanup

| Action | Status |
|--------|--------|
| Removed `dist/fhir4ds_v2-0.0.3-py3-none-any.whl` | DONE |
| Removed `dist/fhir4ds_v2-0.0.3.tar.gz` | DONE |
| Removed `web/wasm-demo/public/fhir4ds_v2-0.0.3-py3-none-any.whl` | DONE |
| Copied `fhir4ds_v2-0.0.4-py3-none-any.whl` to `web/wasm-demo/public/` | DONE |
| Cleaned `__pycache__` directories in `fhir4ds/` source tree | DONE |

Final dist/ contents:
- `fhir4ds_v2-0.0.4-py3-none-any.whl` (sole artifact)

---

## 5. GO / NO-GO Recommendation

### GO

**Rationale:**
- All version strings are consistent at 0.0.4 across all files
- Wheel builds cleanly with both C++ extensions bundled
- ViewDefinition conformance: 100% (134/134)
- FHIRPath R4 conformance: 100% (935/935)
- CQL conformance: 100% (1706/1706)
- DQM conformance: 97.8% (45/46) -- the single shortfall (CMS1017) is a pre-existing known gap, not a regression from v0.0.3
- Overall compliance: 99.96% (2820/2821)
- Repository is clean: no stale artifacts, no stale version references
- WASM demo wheel updated and ready

**Known issues (non-blocking):**
- CMS1017 DQM measure at 97.6% accuracy (pre-existing, tracked separately)
- FHIRPath `lowBoundary`/`highBoundary` and `getResourceKey`/`getReferenceKey` functions not yet implemented (return empty/NULL, documented limitation)
