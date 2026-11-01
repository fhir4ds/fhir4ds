# DOCS AUDIT — S32 WASM conversion-surface parity

- `web/website/docs/getting-started/releases.md` v0.0.18 "WASM runtime parity"
  now documents: ToDate C++ scalar (DATE/VARCHAR bug), the C++ conversion
  mirrors (ToDateTime/ToTime/ToLong/ToRatio/ConvertsTo*/CanConvertQuantity),
  and the three-way expected-vs-desktop-vs-browser harness.
- `AGENTS.md` doctrine: Class A/B split, the Python-authority registration rule
  (`_PYTHON_PREFERRED_CPP_CONFLICTS`), the correctness gate, the
  bare-calendar-keyword grammar, and the open ToQuantity integral-spelling gap.
- `web/wasm-demo` rebuilt with the final wheel + WASM extension; snapshot copied
  to `web/website/static/wasm-app` (wheel `cdcaacf…`, ext `5bc222aa…`).
- Cleanroom targets redeployed via `scripts/deploy_cleanroom_app.sh`; md5
  parity verified.
