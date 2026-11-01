# Engineer Handoff - CQL-12 EXPLORER

Chunk: CQL-12, CQL String Operators.

Resolved implementation changes:
- `fhir4ds/cql/duckdb/macros/list.py`: `CombineSep` now passes
  `COALESCE(sep, '')` to `array_to_string`.
- `fhir4ds/cql/translator/expressions/_lists.py`: string index source
  detection now covers `Combine`, `Replace`, `ReplaceMatches`, and
  `Last(Split(...))`/`Last(SplitOnMatches(...))` so the CQL `Indexer` macro is
  used for derived strings.
- `fhir4ds/cql/translator/expressions/_operators.py`: operator `&` now lowers
  to null-as-empty concatenation with `COALESCE(..., '')`.
- `fhir4ds/cql/duckdb/macros/string.py`: regex-backed string macros now call
  `cqlRegexMatches`, `cqlRegexReplaceMatches`, and `cqlRegexSplitOnMatches`.
- `fhir4ds/cql/duckdb/udf/string.py`: added Python fallback `cqlRegex*`
  helpers with single-line mode, ReDoS guards, and CQL replacement translation.
- `fhir4ds/cql/duckdb/extension.py`: registers Python regex supplements before
  SQL macros are created so native-loaded and forced fallback registrations
  both bind the same macro names.
- `extensions/cql/src/cql_extension.cpp`: added native C++ `cqlRegex*` helper
  UDFs and registered them in the CQL extension.
- `extensions/cql/test/sql/cql.test` and
  `fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py`: added
  regression coverage for null separator, derived string indexers, `&`, and
  advanced regex cases.

Backend coverage:
- Forced Python fallback and native-loaded DuckDB registrations were compared
  for translated string expressions.
- No-Python/browser-style direct SQL macro/UDF behavior was tested.
- Native C++ CQL extension was rebuilt and copied into the package; build and
  bundled CQL extension SHA-256 both equal
  `0aae55b7c85cb939369ae6288c153d60035ef26ba25da5673356c98a8ccd1afa`.

No unresolved engineering items remain from this personality.

