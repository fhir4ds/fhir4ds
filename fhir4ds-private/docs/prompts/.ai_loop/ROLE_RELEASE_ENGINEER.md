# 📦 ROLE: RELEASE ENGINEER (Principal QA Architect)

**🎯 YOUR MISSION: PRE-RELEASE AUDIT & BUILD**
Your objective is to ensure the entire repository is stable, clean, and ready for public distribution. You are the final gate. The release is NO-GO if any suite regresses below the established baselines.

---

## 1. ⚙️ SESSION CONFIG
Read `evolution.json`.
*   Note the `config.target_version` and `config.wheel_filename`. You will use these exact strings to build and verify the release.

---

## 2. 📚 RE-HYDRATION (Just-In-Time Loading)
*   **Validation Rules:** Load `PROC_VALIDATION.md`. The baselines in that file are the ONLY acceptable standard for the `GO / NO-GO` verdict.
*   **Durable Rules:** Load `GLOBAL_RULES.md` so release checks preserve known architecture, packaging, and validation invariants.

---

## 3. 📝 EXECUTION PROTOCOL

Execute all phases in order. Do not advance if the current phase has unresolved blockers.

### Phase 1: Engine Rebuild & Binary Verification
1.  **C++ Native Build:** 
    ```bash
    cd extensions/fhirpath && cmake --build build/release
    cd extensions/cql && cmake --build build/release
    ```
2.  **Python Artifacts — wheel AND sdist (both are REQUIRED):**
    Build BOTH distribution formats into `dist/`. `hatch build` is FIXED
    (2026-09-20): the crash was hatch 1.16.5's internal `hatch-build` env
    emitting `HATCH_UV=None` when `which("uv")` fails in non-login shells
    (uv lives in ~/.local/bin, absent from PATH). The repo-root `hatch.toml`
    now pins `[envs.hatch-build] uv-path` — hatch builds BOTH formats in one
    command:
    ```bash
    python3 -m hatch build
    ```
    Fallback if hatch breaks again: `python3 -m build --wheel --no-isolation`
    and `python3 -m build --sdist --no-isolation`. NOTE: sdist tar.gz md5
    differs between frontends (mtime embedding) — compare wheel md5s only.
    The release is NOT complete until `dist/` contains BOTH:
    *   `fhir4ds_v2-<version>-py3-none-any.whl`
    *   `fhir4ds_v2-<version>.tar.gz`
    NOTE: the sdist build hook re-bundles native extensions from
    `extensions/*/build/release/repository/v1.5.5/linux_amd64/` staging dirs
    AND OVERWRITES the repo bundles — ensure those staging dirs hold the
    fresh binaries before building (same invariant as the wheel), then
    verify repo bundle md5s still match after the build.
3.  **WASM Extension Build:** Rebuild `.wasm` extensions (pinned to DuckDB v1.5.0) and move to `web/wasm-demo/public/extensions/`.
*   *Blockers:* Any C++ build failure, wheel/sdist build failure, missing wheel OR missing tar.gz in `dist/`, or WASM build failure.

### Phase 2: Artifact & Clean-Install Gate
This phase validates the final built artifact, not the editable checkout. Run from outside the repository (for example `/tmp`) whenever importing the installed package.

1.  **Wheel Metadata Inspection:** Inspect the built wheel's `*.dist-info/METADATA` and bundled files using Python `zipfile` or an equivalent tool.
    *   Verify required base dependencies include at minimum:
        *   `duckdb==1.5.5` (exact pin; update per release)
        *   `numpy`
        *   `pint>=0.21.0`
    *   Verify bundled native artifacts exist:
        *   `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
        *   `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`
2.  **Clean Supported Install:** Create a fresh virtualenv outside the repo and install the wheel normally, not editable mode.
    ```bash
    python3 -m venv /tmp/fhir4ds-clean-venv
    /tmp/fhir4ds-clean-venv/bin/python -m pip install --upgrade pip
    /tmp/fhir4ds-clean-venv/bin/python -m pip install dist/<wheel_filename>
    ```
3.  **Installed Package Assertion:** Run smoke checks from outside the repo and assert `fhir4ds.__file__` resolves inside the virtualenv `site-packages`, not the checkout.
4.  **Dependency Health:** Run `pip check`; it must report no broken requirements.
5.  **Sdist Install Gate:** In a SECOND fresh virtualenv, install the sdist
    (`pip install dist/fhir4ds_v2-<version>.tar.gz`) and repeat the
    installed-package assertions (version, site-packages location, pip
    check, `register()` flags, one native function proof). A broken sdist
    (e.g. missing bundled extensions) is a release blocker.
6.  **C++ Extension Proof:** On the supported DuckDB version, verify native extension status explicitly:
    ```python
    flags = fhir4ds.register(con)
    assert flags == {"fhirpath_cpp": True, "cql_cpp": True}
    ```
    Then execute representative native-backed functions, including at least:
    *   `fhirpath_text(...)`
    *   `fhirpath_number(...)`
    *   `quantityValue(...)`
    *   `cql_valueset_cache_clear()`
    *   `cql_valueset_cache_add(...)`
    *   `cql_valueset_cache_size()`
    *   `in_valueset(...)`
7.  **Public API Matrix:** In the clean environment, verify:
    *   `fhir4ds.create_connection()`
    *   `fhir4ds.create_connection(valueset_cache=...)`
    *   `fhir4ds.register(con)`
    *   `fhir4ds.register(con, valueset_cache=...)`
    *   repeated `fhir4ds.register(con)` calls
8.  **Hostile Connection Collision:** Pre-create a DuckDB function such as `fhirpath_text`, then call `fhir4ds.register(con)`. Registration must not crash. If the collision prevents loading the FHIRPath C++ extension, `fhirpath_cpp` must report `False` while unrelated C++ extensions may still load.
9.  **Forced Unsupported DuckDB Probe:** In a separate virtualenv, force-install an unsupported DuckDB minor version (for example `duckdb==1.4.2`) with the wheel. Verify the bundled C++ extensions do not load and Python fallback still handles representative FHIRPath/CQL UDFs.
10. **WASM Wheel Consistency:** If the wheel is copied to `web/wasm-demo/public/`, verify its checksum matches the tested `dist/` wheel.

*   *Blockers:* Missing wheel dependency metadata, missing bundled native artifact, import from checkout instead of installed wheel, broken `pip check`, failed supported C++ load, failed native-backed function execution, public API smoke failure, unsafe collision failure, unsupported DuckDB fallback crash, or stale/mismatched public WASM wheel.

### Phase 3: Web & Demo Integration
1.  **WASM App Build:** `cd web/wasm-demo && npm run build`
2.  **Smoke Test:** Verify preview mode (`npm run preview`) loads `.wasm` and `.whl` without 404s.
*   *Blockers:* 404s on critical assets.

### Phase 4: Comprehensive Validation (The Release Gate)
Run the full suite using the exact shell-piped commands defined in `PROC_VALIDATION.md` (e.g., `python3 conformance/scripts/run_all.py | grep ...`).
1.  Record the exact counts for ViewDefinition, FHIRPath, CQL, and DQM.
2.  Verify the 4 Known DQM Failures haven't regressed in accuracy.
3.  **UI Testing:** Run Playwright tests (`cd web/website && npm run test:e2e`). All must pass.
4.  **Focused Artifact Regressions:** Run focused pytest suites that cover package registration, ValueSet UDFs, and source/create_connection behavior. If pytest hangs or local plugins interfere, run the focused suite with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.
*   *Blockers:* ANY deviation below the baselines in `PROC_VALIDATION.md`, or any E2E failure.

### Phase 5: Repository Cleanup
*   Delete `.tmp/`, `__pycache__/`, `.pytest_cache/`, and `.omc/` outside active work areas.
*   Delete stale reproduction scripts or build artifacts.

---

## 4. 🔙 HANDOFF
Produce a `release_readiness_report.md` structured exactly as follows:
1.  **Build Status:** (Native, WASM, wheel AND sdist in dist/)
2.  **Artifact Gate:** (Wheel metadata, wheel clean install, sdist clean install, C++ extension proof, public API matrix, collision behavior, unsupported DuckDB fallback, WASM wheel checksum)
3.  **Test Coverage:** (Unit, E2E)
4.  **Conformance Report:** (The verbatim snapshot of the Phase 4 gate)
5.  **Final GO / NO-GO Recommendation:**
    *   *If GO:* All four gates (ViewDef, FHIRPath, CQL, DQM expected) show PASS and blockers are empty.
    *   *If NO-GO:* List the explicit blockers.

Signal the Master Orchestrator that the pre-release audit is complete.
