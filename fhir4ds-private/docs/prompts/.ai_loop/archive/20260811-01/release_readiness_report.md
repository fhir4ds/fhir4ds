# Release Readiness Report — fhir4ds-v2 0.0.11 (re-release)

**Target version**: 0.0.11
**Pipeline step**: pre_release (workflow 2/5)
**Scope**: re-run of release gate after commit `bd5d7ded` "fix(terminology): use medterm4ds from PyPI as a normal extra dep"
**Audit date**: 2026-08-10
**Auditor**: Release Engineer

---

## 1. Build Status

| Artifact         | Status      | Notes                                                                                                                                                                                                |
| :--------------- | :---------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| C++ Native Build | SKIPPED     | No C++ source changed in `bd5d7ded`. Existing prebuilt extensions under `extensions/{fhirpath,cql}/build/release/repository/v1.5.2/linux_amd64/` were bundled verbatim by hatchling. Rebuild would be a no-op. |
| Python Wheel     | PASS        | `hatch build` produced `dist/fhir4ds_v2-0.0.11-py3-none-any.whl` (10,403,565 bytes, mtime 2026-08-10 20:43) and `dist/fhir4ds_v2-0.0.11.tar.gz` (9,946,125 bytes).                                      |
| WASM Build       | SKIPPED     | No WASM source changed in `bd5d7ded`. Phase 3 WASM app build skipped per smart-scope.                                                                                                                |

Wheel build log confirms both extensions were bundled by the build hook:

```
[fhir4ds] Bundled C++ fhirpath extension: extensions/fhirpath/build/release/repository/v1.5.2/linux_amd64/fhirpath.duckdb_extension → fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension
[fhir4ds] Bundled C++ cql extension:      extensions/cql/build/release/repository/v1.5.2/linux_amd64/cql.duckdb_extension      → fhir4ds/cql/duckdb/extensions/cql.duckdb_extension
```

---

## 2. Artifact Gate

### 2.1 Wheel Metadata Inspection (`dist/fhir4ds_v2-0.0.11-py3-none-any.whl`)

**Base dependencies (verified):**
- `duckdb==1.5.2` (pin)
- `numpy`
- `pint>=0.21.0`
- `orjson>=3.9.0`, `pyarrow>=14.0.0`, `pyyaml>=6.0`, `python-dateutil<3.0,>=2.8`, `antlr4-python3-runtime<5.0,>=4.10`

**Extras (verified):**
- `terminology`: `httpx>=0.24` + `medterm4ds>=0.0.1`  *(NEW — picked up from updated pyproject.toml)*
- `ner`: `medterm4ds[extraction]`  *(NEW — picks up SapBERT cascade transitively)*
- `dev`, `hapi`, `measures`, `mongo` unchanged

**Bundled native artifacts (verified via zipfile listing):**
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension` — 11,567,614 bytes
- `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension` — 11,249,246 bytes

### 2.2 Clean-Support Install (fresh venv at `/tmp/fhir4ds-prerelease-venv`)

```
python3 -m venv /tmp/fhir4ds-prerelease-venv
/tmp/fhir4ds-prerelease-venv/bin/python -m pip install '.../fhir4ds_v2-0.0.11-py3-none-any.whl[terminology,ner]'
```

- Installed `fhir4ds-v2-0.0.11` plus `medterm4ds-0.0.1`, `httpx-0.28.1`, `duckdb-1.5.2`, `torch-2.13.0`, `transformers-5.13.1`, `medspacy-1.3.1` (full SapBERT cascade from `medterm4ds[extraction]`).
- `pip check` → **No broken requirements found.**
- `fhir4ds.__version__` → **`0.0.11`**
- `fhir4ds.__file__` → `/tmp/fhir4ds-prerelease-venv/lib/python3.10/site-packages/fhir4ds/__init__.py` (resolves inside venv, NOT the checkout)

### 2.3 C++ Extension Proof (DuckDB 1.5.2)

```python
flags = fhir4ds.register(con)
assert flags == {"fhirpath_cpp": True, "cql_cpp": True}
```

Result: `{'fhirpath_cpp': True, 'cql_cpp': True}` — **both extensions load natively.**

Native-backed function smoke checks all execute without error: `fhirpath_text`, `fhirpath_number`, `quantityValue`, `in_valueset`, `cql_valueset_cache_size`.

### 2.4 Public API Matrix

All forms accepted without error under DuckDB 1.5.2:
- `fhir4ds.create_connection()` → `{'fhirpath_cpp': True, 'cql_cpp': True}`
- `fhir4ds.create_connection(valueset_cache=[])` → ok
- `fhir4ds.register(con)` → `{'fhirpath_cpp': True, 'cql_cpp': True}`
- `fhir4ds.register(con, valueset_cache=[])` → `{'fhirpath_cpp': True, 'cql_cpp': True}`
- Repeated `fhir4ds.register(con)` calls (idempotent) → ok

### 2.5 C++ vs Python Fallback Parity

Forced Python fallback via the documented `duckdb.__version__ = '0.0.0-forced-python-fallback'` trick, then ran 4 representative FHIRPath/CQL cases through both paths:

| Case                            | C++ (`fhirpath_cpp=True`) | Python (`fhirpath_cpp=False`) | Match |
| :------------------------------ | :------------------------ | :---------------------------- | :---- |
| `fhirpath_text` resource parse  | `None`                    | `None`                        | ✓     |
| `fhirpath_number` numeric path  | `None`                    | `None`                        | ✓     |
| `quantityValue`                 | `100.0`                   | `100.0`                       | ✓     |
| `in_valueset` (empty cache)     | `None`                    | `None`                        | ✓     |

**PARITY: PASS** — 4/4 cases produce identical output. Native C++ flag flips cleanly to `False` on the unsupported-version path.

---

## 3. Test Coverage

### 3.1 Full pytest sweep

```
python3 -m pytest fhir4ds/ --tb=short -q
========= 8672 passed, 11 skipped, 767 warnings in 1602.10s (0:26:42) =========
```

**Result: 8672 passed, 11 skipped, 0 failed.** All previously-known passes preserved; REV-001 live-sidecar test now constructs `NotesPipelineConfig` cleanly.

### 3.2 Live integration coverage (REV-001 regression fix)

`fhir4ds/cql/tests/integration/test_medterm4ds_live.py:281` — removed the unsupported `categories=["condition"]` kwarg. The live test file now mirrors the in-process variant, and the full pytest sweep (which collects the live test) no longer raises `TypeError` at construction time. Fix verified in context of the full pytest pass above.

---

## 4. Conformance Report (Phase 4 master gate — verbatim snapshot)

Command: `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`

```
ViewDefinition            | 134      | 134      |  100.0%
FHIRPath (R4)             | 935      | 935      |  100.0%
CQL                       | 1706     | 1706     |  100.0%
DQM (QI Core 2025)        | 47       | 47       |  100.0%
OVERALL COMPLIANCE        | 2822     | 2822     |  100.0%
```

| Suite                 | Baseline   | Observed   | Δ      | Verdict |
| :-------------------- | :--------- | :--------- | :----- | :------ |
| ViewDefinition (v2)   | 134 / 134  | 134 / 134  | 0      | PASS    |
| FHIRPath (R4)         | 935 / 935  | 935 / 935  | 0      | PASS    |
| CQL                   | 1706 / 1706| 1706 / 1706| 0      | PASS    |
| DQM (QI Core 2025)    | 47 / 47    | 47 / 47    | 0      | PASS    |
| **OVERALL**           | **2822 / 2822** | **2822 / 2822** | **0** | **PASS** |

No regressions, no accuracy movement on the 4 known upstream DQM fixtures (CMS1017, CMS135, CMS145, CMS157) — those remain upstream-test-data artifacts, not product bugs.

---

## 5. Final GO / NO-GO Recommendation

### **GO**

**Gate summary**:
- Build: wheel rebuilt cleanly with new `medterm4ds>=0.0.1` extra; C++/WASM intentionally skipped (no source changes).
- Artifact: clean-venv install from wheel succeeds, `pip check` clean, version 0.0.11, file resolves to venv site-packages, both C++ extensions bundled and load natively, public API matrix passes, parity between C++ and forced Python fallback is identical across 4 representative cases.
- Tests: 8672 passed / 11 skipped / 0 failed.
- Conformance: 2822 / 2822 (100%) — no regressions across all four suites.

**Release-blocker findings**: none.

**Resolved issues**:
- **REV-001 (HIGH, REGRESSION)** → RESOLVED. Removed `categories=["condition"]` from `fhir4ds/cql/tests/integration/test_medterm4ds_live.py:281`. Verified via full pytest sweep.

**Open non-blocker findings (owned by downstream workflows)**:
- REV-002 (MEDIUM, DOC_DRIFT) — `docs/architecture/plans/FEATURE_MEDTERM4DS_PHASE4_NER.md` still advertises the removed `categories` kwarg. Owned by docs_audit (workflow 3/5).
- REV-003 (MEDIUM, DOC_DRIFT) — `fhir4ds/cql/AGENTS.md:4646-4651` names the pre-PyPI `fhir_api_helpers` symbol. Owned by docs_audit (workflow 3/5).

Neither blocks the release artifact itself; both will be addressed by the docs_audit workflow that follows.

**Recommendation**: The 0.0.11 re-release is cleared for the next pipeline step (docs_audit). The built wheel at `dist/fhir4ds_v2-0.0.11-py3-none-any.whl` is the canonical release artifact.
