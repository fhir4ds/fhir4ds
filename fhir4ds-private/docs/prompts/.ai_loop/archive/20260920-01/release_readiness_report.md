# Release Readiness Report — fhir4ds-v2 0.0.15

**Date**: 2026-09-20
**Target version**: 0.0.15
**Pipeline**: dependency_upgrade → bug_fix → evolution (36 iters) → code_review → **pre_release**
**DuckDB pin**: 1.5.5 (upgraded from 1.5.2 in dependency_upgrade workflow)

---

## 1. Build Status

| Item | Status | Evidence |
|------|--------|----------|
| Version bump | ✅ DONE | pyproject.toml + 7 subpackage `__init__.py` = 0.0.15; `fhir4ds/tests/test_version.py` 2/2 PASS |
| Wheel build | ✅ DONE | `dist/fhir4ds_v2-0.0.15-py3-none-any.whl`, md5 `a9ba3e3a8c26f6ed42eca0ee36687c26`, built via `python3 -m build --wheel --no-isolation` (hatch build broken on this box — EnvVars TypeError) |
| Sdist build | ✅ DONE | `dist/fhir4ds_v2-0.0.15.tar.gz` (10.9 MB) built via `python3 -m build --sdist --no-isolation`; bundles both native extensions; clean-venv install PASS (version 0.0.15, register() both True, fhirpath_text + cqlDivide native proofs, pip check clean) — added post-GO per Joel |
| Bundled extensions | ✅ FRESH | fhirpath `fd81a7c2…` + cql `4e4ff1e3…` — match repo bundles exactly; staging-dir staleness caught and fixed (repository/v1.5.5/linux_amd64 dirs re-synced from build/release/extension outputs) |
| Wheel metadata | ✅ VERIFIED | duckdb==1.5.5, numpy, pint>=0.21.0, orjson, antlr4, dateutil, pyarrow, pyyaml; medterm4ds[extraction] 0.0.4<0.0.5 (ner) + medterm4ds 0.0.4<0.0.5 (terminology) |

## 2. Artifact Gate

| Check | Result |
|-------|--------|
| Clean venv install (py3.10) | ✅ pip check clean; `import fhir4ds` OK; `__version__` == 0.0.15 |
| `register(con)` | ✅ `{'fhirpath_cpp': True, 'cql_cpp': True}`; idempotent ×3 |
| Native function proofs | ✅ fhirpath_text 'Alice', fhirpath_number 42, quantityValue 3.5, cql_valueset_cache add/size, in_valueset 3-arg TRUE, cqlDivide exact |
| Unsupported duckdb (1.4.2) | ✅ Both flags False, Python fallback serves fhirpath_text + cqlDivide correctly |
| Macro collision | ✅ Pre-created user macro doesn't crash register; user macro shadows until DROP |
| WASM assets | ✅ wasm-demo public 0.0.15 wheel + wasm extensions (cql `11b358b3…`, fhirpath `0e26a1aa…`); cql-clinic public refreshed to 0.0.15; bulk-publisher-app wheel + duckdb-eh.wasm + worker.js + extensions refreshed |
| Static snapshots | ✅ website static/wasm-app + static/cql-clinic-app rebuilt from fresh dist (0.0.15 everywhere); build/ regenerated — 5/5 wheels in build tree all md5 `a9ba3e3a…` |

## 3. Test Coverage

| Suite | Result |
|-------|--------|
| Website e2e (`web/website`) | ✅ **19/19 passed** (incl. bulk-publish DuckDB+Pyodide boot after stale-build fix) |
| wasm-demo mandated e2e (playground + web-component + cms-measures) | ✅ **23/23 passed** (full 70-test run: 63 pass; 7 failures are external-credential Epic/Cerner sandbox tests — environment-dependent, not wheel-related) |
| Website typecheck | ✅ EXIT 0 |
| Website build | ✅ EXIT 0 (one pre-existing benign duckdb-wasm critical-dependency WARNING) |
| wasm-demo build / cql-clinic build | ✅ EXIT 0 |

## 4. Conformance Report

Master gate (`conformance/scripts/run_all.py`, duckdb 1.5.5, final tree):

```
2832/2832 PASSED
  ViewDefinition: 144/144
  FHIRPath:       935/935
  CQL:           1706/1706
  DQM:             47/47
```

## 5. Final GO/NO-GO

## ✅ **GO**

0.0.15 is release-ready: version triple consistent, wheel bundles fresh native
extensions matching repo, clean-install + unsupported-version fallback gates
green, conformance 2832/2832, all browser surfaces verified green on the
0.0.15 wheel.

### Notes for docs_audit (next workflow)
- BUGFIX-005 (D1-D8 docs one-liners) lands in docs_audit per bug_fix deferral.
- Notebooks must be executed against the 0.0.15 wheel.
- python3.11 clean-install leg deferred to CI (no python3.11 on this box) — same
  as 0.0.13.
- Known LOW follow-ups filed during code_review: REV-020 (bool coercion in
  CloudCredentials.configure), REV-021 (JSON-list UDF name tuple duplication).
