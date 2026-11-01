# Engineer Handoff: FP-10 EXPLORER

## Issue Triage

| Issue | Severity | Category | Status |
|---|---|---|---|
| QA-001 | MEDIUM | SPEC_VIOLATION | RESOLVED |

## Root Cause

Native C++ `fn_upper`/`fn_lower` use hand-maintained UTF-8 case mapping. Prior FP-10 fixes covered ASCII, Latin-1, most Latin Extended-A, basic Greek, and Cyrillic, but the table still missed common Unicode special cases:
- Dotted capital I `İ` lowercases to `i` + combining dot above.
- Dotless small i `ı` uppercases to `I`.
- Accented Greek vowels `άέήίόύώ` uppercase to `ΆΈΉΊΌΎΏ`, and the reverse for lowercase.

Spec basis: FHIRPath §5.6.6/§5.6.7 require `upper()`/`lower()` to convert all characters in the input string to upper/lower case. Public DuckDB behavior also needs native C++ and forced Python fallback parity.

## Fix

Changed `extensions/fhirpath/src/fhirpath/evaluator.cpp`:
- Added native mappings for U+0130 and U+0131.
- Added native mappings for accented Greek vowels U+03AC/U+03AD/U+03AE/U+03AF/U+03CC/U+03CD/U+03CE and U+0386/U+0388/U+0389/U+038A/U+038C/U+038E/U+038F.
- Added Greek dialytika pairs U+03CA/U+03CB and U+03AA/U+03AB while in the same mapping block.

Added/updated coverage:
- `fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`
- Fresh QA probe `.temp/qa/fp10_explorer_probe.py`

Rebuilt the native extension and copied it into `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`. Build and bundled hashes match.

## Validation

- `.temp/qa/fp10_explorer_probe_after_fix.log`: 47 cases, 0 mismatches, 0 failures.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py -q`: 4 passed.
- `./build/release/test/unittest '*fhirpath*'`: 478 assertions passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Notes

No new issues were discovered during remediation. `spec_schedule.json` and archive files were not modified.
