# Architect Handoff — FP-01 HISTORIAN

## Structural Health

Healthy. The fix is localized to the FHIRPath literal-unescape boundary in the
Python fallback and native C++ lexer. It does not add wrapper-specific hacks,
does not broaden arbitrary syntax-error behavior, and keeps native/fallback
validity aligned for the §4.1 string-literal edge. The bundled native extension
was rebuilt and copied, so package behavior matches source.

## Issue Counts

- `SPEC_VIOLATION`: 1 found, 1 resolved, 0 open.
- `API_CONTRACT`: 0.
- `DATA_HANDLING`: 0.
- `REGRESSION_RISK`: 0 new findings.

## QA Audit

QA was sufficient. It covered all FP-01 literal families, verified the
normative HL7 FHIRPath §4.1 language before logging the issue, compared native
and forced Python fallback paths, and explicitly discarded non-bugs such as
uppercase `True` being an identifier and calendar quantity output preserving
`4 days`. No `RETRY_QA` flag is needed.

## Handoff Compression

Fresh HISTORIAN QA found `QA-001`: unpaired Unicode surrogate string escapes
such as `'\uD834'` were considered valid and later failed as invalid Unicode in
DuckDB/Python materialization. Remediation added surrogate-pair validation to
Python `_unescape_fhirpath_string()` and native `appendUnicodeEscape()`, kept
malformed non-surrogate escapes like `\u005` as existing plain text behavior,
added parity/native tests, rebuilt the bundled extension, and validated
FHIRPath plus full conformance.

## Validation Reviewed

- `.temp/qa/fp01_historian_fresh_probe.py` — PASS.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py -q` — 19 passed.
- `./build/release/test/unittest "*fhirpath*"` — 716 assertions passed.
- `python3 conformance/scripts/run_fhirpath_r4.py`; report parsed as 935/935.
- Full conformance filtered command — 2822/2822 overall.

## Recommended Fix Order

No further engineer pass is recommended for FP-01 HISTORIAN. Continue to the
outer spec-compliance orchestrator.
