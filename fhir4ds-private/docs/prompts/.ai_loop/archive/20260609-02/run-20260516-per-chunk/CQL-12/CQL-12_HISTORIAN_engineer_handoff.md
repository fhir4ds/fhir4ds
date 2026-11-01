# Engineer Handoff - CQL-12 HISTORIAN

Chunk: CQL-12, CQL String Operators.

Resolved implementation changes:
- `fhir4ds/cql/duckdb/macros/string.py`: `Matches` now calls `regexp_matches(..., 's')`, `ReplaceMatches` now calls `regexp_replace(..., 'gs')`, and `SplitOnMatches` now calls `regexp_split_to_array(..., 's')` so CQL regex operators use single-line mode.
- `fhir4ds/cql/duckdb/udf/string.py`: deprecated `stringMatches` now returns NULL for null patterns and uses `re.DOTALL`; deprecated `stringReplace` returns NULL for null old/new operands.
- `fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py`: added translated and direct no-Python/browser-style dot-crosses-newline regression coverage, plus direct legacy UDF parity probes.

Backend coverage:
- Translated `Matches`, `ReplaceMatches`, and `SplitOnMatches` were executed on forced Python fallback and native-loaded DuckDB registrations.
- Direct SQL macro coverage was executed on no-Python/browser-style registration.
- Deprecated direct Python UDFs were compared between forced Python fallback and native-loaded registration.
- Native C++ CQL unittest was run; no C++ source rebuild was required because the changes are Python macro/UDF/test changes.

No unresolved engineering items remain from this personality.
