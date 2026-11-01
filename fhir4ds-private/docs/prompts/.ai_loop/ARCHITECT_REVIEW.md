# ARCHITECT REVIEW — WASM function-surface parity (self-audit)

## Invariants the feature must preserve

1. **Desktop is the conformance authority.** `register()` keeps loading the
   Python UDFs/macros exactly as today; C++ mirrors are additive for the
   no-Python (WASM) path. Desktop results for the existing test corpus must not
   change (byte-identical SQL; identical values/types).
2. **VARCHAR transport.** CQL Date/DateTime/Time/Quantity/Ratio values travel
   as VARCHAR/JSON text. Native `ToDate`/`ToDateTime`/`ToTime` must return
   VARCHAR; native `ToLong` returns BIGINT; `ToRatio` returns Ratio JSON text.
   No function may leak DATE/TIMESTAMP/TIME result types into translated SQL.
3. **Null semantics.** `ConvertsTo*(NULL)` → SQL NULL; `To*(invalid)` → NULL;
   none of the ports may raise at the SQL boundary (row-resilient).
4. **Fixtures outrank prose.** The corpus must include the official fixture
   behaviors already pinned in this repo (e.g. `ToTime` normalizes and drops a
   timezone suffix; `ToDateTime` maps `Z` to `+00:00`).
5. **No translator changes.** This is a runtime-surface completion; translated
   SQL for the existing corpus must remain byte-identical.
6. **Single source per transport.** Class A macros must be semantically
   identical on both surfaces (prefer verbatim SQL); Class B functions have one
   C++ implementation serving the browser.
7. **Contract test must be falsifiable.** The upgraded test must fail when a
   TS macro body drifts or a new desktop function lacks a browser/native
   counterpart; allowlist entries stay justified and pruned.
8. **Artifact parity.** Native and WASM extensions are rebuilt together and
   md5-verified in build/bundle/site-packages/public; the wheel is rebuilt
   before any deploy.

## Skeptical notes on the v1 draft

- **S1 (HIGH) — "48 missing" overstates the actionable set.** Classify before
  porting: 22 names are the documented list-equality/terminology allowlist; the
  actionable set is the conversion family. The FDD must carry the exact table
  (Class A/B/C) so implementation does not chase allowlisted names.
- **S2 (HIGH) — type comparison is load-bearing.** The ToDate defect was a TYPE
  difference (DATE vs VARCHAR), not a value difference. The harness must record
  `typeof(...)` alongside the value.
- **S3 (MEDIUM) — Class A inventory needs verification.** `ConvertsToInteger` /
  `ConvertsToString` exist on both sides; decide copy-vs-keep by body diff, not
  assumption. The draft currently hedges in two places.
- **S4 (MEDIUM) — `ToInterval`/`ToPrevalenceInterval` are not CQL Appendix B
  operators.** Confirm they are library-defined/translator extensions; if they
  are not spec surface, exclude them explicitly from scope.
- **S5 (MEDIUM) — `CanConvertQuantity` may not be emitted.** Confirm translator
  reachability; keep the port only if it is reachable or public surface used by
  direct SQL; otherwise allowlist with a note.
- **S6 (LOW) — harness must execute the TS macros verbatim.** Reusing the
  macro-sync regex is correct; do not hand-copy macro SQL into the harness.
- **S7 (LOW) — red→green evidence per function.** Each port lands with a
  browser-path test that fails before the C++ registration and passes after.

## Required refinements (applied in v2)

- Add the explicit Class A/B/C table with per-function decisions.
- Require `(value, typeof)` parity in the harness.
- Add the translation-byte-identity guard to the test plan.
- Add `ExpandValueSet`/list-equality as explicit non-goals for this campaign.
- Add per-function red→green acceptance evidence to the implementation steps.
- Add artifact/gate checklist to the handoff.
