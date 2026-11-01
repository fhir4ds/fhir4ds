# QA Handoff - CQL-12 EXPLORER

Chunk: CQL-12, CQL String Operators.

Personality: EXPLORER.

Scope independently tested:
- Official and adversarial string operator behavior for `Combine`, `Concatenate`,
  `Indexer`, `Matches`, `ReplaceMatches`, `Split`, `SplitOnMatches`,
  `StartsWith`, `EndsWith`, and `Substring`.
- Translated CQL execution against forced Python fallback and native-loaded
  DuckDB registrations.
- No-Python/browser-style direct SQL macro/UDF behavior for the public CQL
  DuckDB extension surface.
- Native C++ implementation and bundled extension freshness after adding native
  regex helper UDFs.

Issues found:
- `QA-CQL12-EXPLORER-001`: `Combine({'a','b'}, null)` used DuckDB's comma
  default separator instead of CQL's empty separator.
- `QA-CQL12-EXPLORER-002`: derived string indexers over `Combine`,
  `ReplaceMatches`, and `Last(Split(...))` were routed through list extraction
  and returned empty strings at boundary indexes.
- `QA-CQL12-EXPLORER-003`: translated CQL `&` used null-propagating SQL `||`
  instead of null-as-empty concatenation.
- `QA-CQL12-EXPLORER-004`: regex-backed operators did not support
  backreferences/lookahead consistently across native C++ and Python fallback
  public surfaces.

No open QA issues remain for this personality.

Validation:
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py -q` -> 4 passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py fhir4ds/cql/duckdb/tests/integration/test_wasm_translate_execute_gate.py -q` -> 12 passed.
- `./build/release/test/unittest "*cql*"` from `extensions/cql` -> 672 assertions in 2 test cases.
- `python3 conformance/scripts/run_cql.py` -> 1706/1706 passed.
- `python3 conformance/scripts/run_all.py` -> 2822/2822 passed overall.
- `python3 -m pytest fhir4ds -q` -> 7179 passed, 5 skipped, 9 warnings.
- `git diff --check` -> passed.

