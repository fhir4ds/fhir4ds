# Architect Handoff: CQL-22 SKEPTIC

Golden standard captured in `.temp/architect/golden_standard.md`: translated public CQL helpers must exist in Python fallback, native-loaded, and no-Python/browser-style runtimes; `Message` must return source except true-condition Error severity; no-Python execution may depend only on compiled UDFs and pure SQL macros.

Audit result: structurally sound. The fix places `CQLMessage` in the Tier 1 macro registry, exactly where no-Python runtime support belongs, and leaves translator semantics intact. The small compatibility guard in `registerMathUdfs()` prevents the new macro from breaking legacy Python UDF registration. No fixture-specific logic, FHIR/profile assumptions, or SQL string post-processing were introduced.

QA quality: sufficient. The probe covered false/null conditions, non-Error severities, Error runtime failures, primitive/list/JSON-shaped source preservation, translated CQL, and Python fallback/native-loaded/no-Python parity. No `RETRY_QA` is needed.

Issue status:
- `CQL22-SKEPTIC-001`: VERIFIED.

Recommended next step:
- Clean exit for this inner loop pass; continue CQL-22 with HISTORIAN.
