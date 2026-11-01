# Release Readiness Report — v0.0.16

Date: 2026-09-20
Role: Release Engineer (pre_release pipeline step)

## 1. Build Status

- **Native extensions**: no C++ changes this release (Python-only campaign);
  staged binaries verified md5-identical to repo bundles
  (fhirpath fd81a7c2…, cql 4e4ff1e3…; staging
  `extensions/*/build/release/repository/v1.5.5/linux_amd64/` == repo bundles
  before AND after build-hook re-bundling).
- **Wheel**: `dist/fhir4ds_v2-0.0.16-py3-none-any.whl` (11,374,555 bytes,
  md5 a040c7aa957b4bc89bb08fd0f956c904) built via `python3 -m hatch build`
  (both formats in one command).
- **Sdist**: `dist/fhir4ds_v2-0.0.16.tar.gz` (10,885,277 bytes) present.
- **WASM**: not rebuilt this pass — Python-only release; WASM/website assets
  assigned to docs_audit per campaign directives (consistent with 0.0.12/0.0.13
  pattern where docs_audit refreshes the public wheel).

## 2. Artifact Gate

- **Wheel metadata**: Version 0.0.16; Requires-Dist includes duckdb==1.5.5,
  numpy, pint>=0.21.0 (plus antlr4, python-dateutil, pyarrow, orjson, PyYAML);
  extras intact (terminology/ner medterm4ds >=0.0.4,<0.0.5).
- **Bundled natives**: both duckdb_extension files present in the wheel.
- **New modules shipped**: `fhir4ds/cql/translator/type_map.py`,
  `fhir4ds/cql/types/typeref.py`; deleted stubs confirmed absent
  (`cql/types/{cql_types,fhir_types,type_checker}.py`).
- **Wheel clean install** (/tmp/fhir4ds-clean-venv): version 0.0.16 from
  site-packages; pip check clean; register flags
  `{'fhirpath_cpp': True, 'cql_cpp': True}` (idempotent on re-register);
  native proofs pass (fhirpath_text, fhirpath_number, quantityValue,
  valueset cache trio, in_valueset); public API matrix OK
  (create_connection, valueset_cache variants, register).
- **Hostile collision**: pre-created `fhirpath_text` macro → register does not
  crash, flags degrade to False. Pass.
- **Facade smoke (clean wheel)**: `1 + 2` → valueInteger 3;
  `Sum({1 'ml',2 'ml',3 'ml'})` → valueQuantity 6 ml;
  `years between DateTime(2005) and DateTime(2010)` → interval [4,5] parts.
  Metadata-first serializer active (flag default True).
- **Sdist clean install** (/tmp/fhir4ds-sdist-venv): version 0.0.16,
  site-packages resolution, pip check clean, both C++ flags True, native
  function proof pass.
- **Unsupported DuckDB probe** (duckdb==1.4.2, wheel installed --no-deps):
  flags correctly False (no crash), Python fallback serves
  fhirpath_text and cqlDivide. Note: pip reports the expected
  dependency-conflict warning against the duckdb==1.5.5 pin — intended
  (exact-pin doctrine).
- **WASM wheel consistency**: deferred to docs_audit (public wheel refresh).

## 3. Test Coverage

- cql unit tree: 1708 passed (incl. 46 type_map tests, 10 serializer tests,
  drift tripwire).
- Version consistency: fhir4ds/tests/test_version.py 2/2.
- DQM-47 SQL baseline compare: BYTE-IDENTICAL 47/47 (metadata-only guarantee).
- Legacy snapshot diff (1049 defines): EMPTY (verbatim compat port).
- Playwright E2E: deferred to docs_audit (website assets not yet refreshed).

## 4. Conformance Report (Phase 4 gate, verbatim)

```
ViewDefinition            | 144      | 144      |  100.0%
FHIRPath (R4)             | 935      | 935      |  100.0%
CQL                       | 1706     | 1706     |  100.0%
DQM (QI Core 2025)        | 47       | 47       |  100.0%
OVERALL COMPLIANCE        | 2832     | 2832     |  100.0%
SUCCESS: 100% Spec Conformance Achieved!
```

## 5. Final Recommendation: **GO**

All four suites PASS at 100%; blockers empty. Remaining cosmetic items
(type_map.py trailing newline) are non-blocking. WASM/website/E2E follow-ups
are docs_audit scope per campaign directives.
