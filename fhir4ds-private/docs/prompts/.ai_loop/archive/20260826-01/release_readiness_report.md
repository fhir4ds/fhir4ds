# Release Readiness Report — fhir4ds-v2 0.0.12 (2026-08-24)

## 1. Build Status
- **Native C++**: no native source changes this release cycle (campaign diff is pure Python); bundled extensions rebuilt from existing verified binaries (fhirpath `57d0634b…`, cql `c5b22d58…` — same hashes as the milestone-#10-verified pair).
- **Wheel**: `dist/fhir4ds_v2-0.0.12-py3-none-any.whl` built via hatch with both extensions bundled; rebuilt after the subpackage version-constant bump.

## 2. Artifact Gate
- **Version bump**: pyproject 0.0.11→0.0.12, root `__version__`, and all 6 subpackage version constants (cql, cql.duckdb, dqm, fhirpath, fhirpath.duckdb, viewdef) — `test_public_subpackage_versions_match_root` 2/2.
- **Wheel metadata**: base deps `duckdb==1.5.2`, `numpy`, `pint>=0.21.0`, `pyarrow>=14.0.0`, `orjson`, antlr4, dateutil, pyyaml. **medterm4ds bound ships exactly as mandated**: `medterm4ds>=0.0.2,<0.0.3` (terminology extra) and `medterm4ds[extraction]>=0.0.2,<0.0.3` (ner extra).
- **Bundled native artifacts**: both `.duckdb_extension` files present in wheel.
- **Extension md5s**: repo == wheel == site-packages for BOTH extensions (`57d0634b6ee6eddee9fc06a1355bef5a`, `c5b22d58310c1eb7bafa17ce7877f989`).
- **Clean install** (fresh venv outside repo): resolves in site-packages (not checkout), version 0.0.12 across root+subpackages, `pip check` = "No broken requirements found."
- **C++ extension proof**: `register()` flags `{fhirpath_cpp: True, cql_cpp: True}`; native functions executed: `fhirpath_text`, `fhirpath_number`, `quantityValue`-family (parse_quantity), `cql_valueset_cache_clear/add/size`, `in_valueset` (True on matching coding).
- **Public API matrix**: `create_connection()`, `create_connection(valueset_cache=...)`, `register(con)`, `register(con, valueset_cache=...)`, repeated `register(con)` — all clean.

## 3. Test Coverage
- Focused artifact regressions (PYTEST_DISABLE_PLUGIN_AUTOLOAD): test_version + input-validation + sources suites green post-bump.
- Campaign suites: loader 76/76, filesystem 41/41, audit-mode 31/31, CQL unit+integration 1867 passed/0 failed (first fully-green run — MT-008 fixed), medterm 230 passed/4 skip-note.

## 4. Conformance Report (verbatim, PYTHONPATH=/mnt/d/fhir4ds)
```
ViewDefinition            | 144      | 144      |  100.0%
FHIRPath (R4)             | 935      | 935      |  100.0%
CQL                       | 1706     | 1706     |  100.0%
DQM (QI Core 2025)        | 47       | 47       |  100.0%
OVERALL COMPLIANCE        | 2832     | 2832     |  100.0%
```
Note: gate ran immediately before the 6 subpackage version-string constants were bumped (the focused version tests re-verified after; string-only change, no behavior).

## 5. Final Recommendation: **GO**
All four suites PASS at/above baseline; blockers empty. Scope note per USER_DIRECTIVES: WASM/website integration (wheel copy to web/wasm-demo, PRODUCT_VERSION, releases.md, demo.spec.ts, typecheck+build) is assigned to the docs_audit workflow, which owns `web/website/AGENTS.md` compliance including the micropip `deps=False` rule.
