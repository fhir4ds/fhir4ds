# Engineer Handoff — SOF-VD-02 (HISTORIAN), iteration 1

## Triage
| Issue | Category | Verdict |
|---|---|---|
| QA-001 MEDIUM: exponent-notation decimal substitution -> invalid FHIRPath literal -> silent empty | SPEC_VIOLATION | RESOLVED |
| QA-002 MEDIUM: json.loads float rounding corrupts decimal constants | SPEC_VIOLATION | RESOLVED |

## Fixes (root cause, no shims)
- **QA-001** `fhir4ds/viewdef/constants.py::_resolve_simple_value`: new decimal branch serializes value in plain fixed-point notation (`Decimal` + `format(d,'f')`), using `repr()` for float inputs (shortest round-trip, no binary-expansion noise), and appends `.0` when integral so the literal always lexes as a FHIRPath Decimal (never an out-of-32-bit Integer). Spec: SQL-on-FHIR v2 IG constant.value[x] "effectively converts the FHIR literal defined here to a FHIRPath literal"; FHIRPath N1 grammar Number literal has no exponent. Both engines accept plain notation at any magnitude (verified natively and via fallback: `0.0000001 < 0.001` -> true, `1000000000000000000000.0 > 5` -> true).
- **QA-002** `fhir4ds/viewdef/parser.py::parse_view_definition`: `json.loads(..., parse_float=Decimal)`; `12345678901234567890.12345` now round-trips verbatim into the substituted literal (FHIR decimal precision = 18 digits preserved).
- Python-only change; no native dual-engine edit needed (engines already agree; the bug was in textual substitution).

## Tests
- `fhir4ds/viewdef/tests/unit/test_constants.py`: + `TestDecimalPlainNotation` (7), + `TestDecimalLosslessParsing` (2, incl. end-to-end generate assertion `0.00001 < 0.001` in SQL, no `1e-05`).
- `fhir4ds/viewdef/tests/test_spec_compliance.py::test_constant_decimal`: assertion updated to `Decimal("1.2")` (Decimal != float exact — old assertion pinned the lossy float parse).

## Validation (fresh, FINAL tree, PYTHONPATH=/mnt/d/fhir4ds)
- viewdef pytest: 1168/1168.
- Master gate: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2832/2832.
- Reproducers (probe2/probe3) now return correct booleans end-to-end in DuckDB (fallback + native extension agree).
- Binaries unchanged: fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a (repo bundle == site-packages). NOTE: repo constants.py md5 376c9a2845c76f6d6f70bba575a503ea differs from stale site-packages copy (2d4dd388...); master gate re-run with PYTHONPATH=repo confirms final tree.
- Environment note: `register_fhirpath()` returned False on fresh connections (unsigned extension); native probed via `duckdb.connect(config={"allow_unsigned_extensions": True})` + LOAD.
