# PRE-RELEASE GATE — S32 WASM conversion-surface parity (0.0.18)

- Version: `0.0.18` consistent across `pyproject.toml`, 7 `__init__` files,
  website PRODUCT_VERSION, notebook pins (`test_version` in the pytest tree).
- Native cql extension `bd8ec2890912b623faff4c24d8ceb4b7` (build == repo bundle
  == site-packages).
- WASM cql extension `5bc222aa060a68495d44ac89c0dd4672` (build == cleanroom
  public == wasm-demo public == deployed static targets).
- Wheel `fhir4ds_v2-0.0.18-py3-none-any.whl` `cdcaacf27809cf321552616e62404a9e`
  (contains `bd8ec289…`), present at both roots and `assets/` of
  `fhir4ds/devserver/static-cleanroom` and `web/website/static/cql-cleanroom`,
  plus `web/wasm-demo`, `web/website/static/wasm-app`, and
  `web/website/static/bulk-publisher-app` snapshots.
- Clean venv: install OK, `pip check` clean, `register()` native, ToDate/
  ToDateTime/ToLong/ToRatio/ConvertsToQuantity smoke correct.
- Master conformance **2832/2832** (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).
- cql suites (chunked, fresh processes): 2232 + 734 + 228 = **3194 passed**,
  10 skipped, 1 xfail.
- fhirpath/viewdef/dqm/devserver/operations/tests: **4046 passed**, 2 failures
  are the documented pre-existing FHIRPath parity gaps (FP-14/FP-10; fhirpath
  binary untouched).
- Vitest 197. Standalone CMS125 cells clean.
- Note: the one-shot full-tree run died with a WSL/drvfs **SIGBUS** during
  DuckDB extension registration; the same file passed 77/77 in isolation and
  the chunked reruns are green (environment flake, not a code failure).
