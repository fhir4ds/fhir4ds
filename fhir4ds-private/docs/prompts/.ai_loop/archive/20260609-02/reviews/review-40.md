# Review-40 Code Review Findings

Active milestone review after 40 completed spec chunks. I used current source, active state files, AGENTS.md, GLOBAL_RULES.md, GLOBAL_KNOWLEDGE.md, ARCHIVE_LOG.md, current tests, and freshly run validation. I did not use archived workflow outputs as proof of behavior.

## Findings

### REV-001 — HIGH — RESOLVED — Direct list UDF overloads diverge between forced Python and native/no-Python C++

The direct DuckDB list helper surface is not parity-complete for non-string list element types. The Python fallback registers polymorphic Python UDFs for `SingletonFrom`, `ElementAt`, and `jsonConcat` in `fhir4ds/cql/duckdb/udf/list.py:197`, `fhir4ds/cql/duckdb/udf/list.py:203`, and `fhir4ds/cql/duckdb/udf/list.py:211`. The C++ extension registers only `VARCHAR[]` overloads for `SingletonFrom` and `ElementAt`, and only VARCHAR/VARCHAR-list overloads for `jsonConcat`, at `extensions/cql/src/cql_extension.cpp:6332`, `extensions/cql/src/cql_extension.cpp:6334`, and `extensions/cql/src/cql_extension.cpp:6338`.

Fresh reproducer from the current checkout:

```text
SELECT SingletonFrom([1])
  forced Python: ('1',)
  native-loaded C++: BinderException: no function matches SingletonFrom(INTEGER[])
  no-Python C++: BinderException: no function matches SingletonFrom(INTEGER[])

SELECT ElementAt([1,2,3], 1)
  forced Python: ('2',)
  native-loaded C++: BinderException: no function matches ElementAt(INTEGER[], INTEGER_LITERAL)
  no-Python C++: BinderException: no function matches ElementAt(INTEGER[], INTEGER_LITERAL)

SELECT jsonConcat([1], [2])
  forced Python: (['1', '2'],)
  native-loaded C++: BinderException: no function matches jsonConcat(INTEGER[], INTEGER[])
  no-Python C++: BinderException: no function matches jsonConcat(INTEGER[], INTEGER[])
```

The existing parity coverage only checks string-list direct calls: `fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py:251` and `fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py:105`. Python-only unit coverage does exercise integer `SingletonFrom([1])` at `fhir4ds/cql/duckdb/tests/test_list_udfs.py:204`, so the gap is specifically missing native/no-Python parity coverage for the same public helper shape.

Recommended remediation:

- Add native/no-Python C++ coverage for integer, decimal/double, boolean, and string list inputs for `SingletonFrom` and `ElementAt`, including multi-item error behavior.
- Add C++ overloads or a pure SQL macro strategy so these helpers bind on non-string lists with the same public behavior as forced Python fallback.
- Add `jsonConcat` parity coverage for non-string lists, or deliberately narrow the Python fallback to the same supported public type surface if this helper is intended to be JSON/string-only.

Resolution:

- Added native C++ generic list/scalar handling for non-string public direct helper calls: `SingletonFrom(LIST<ANY>)`, `ElementAt(LIST<ANY>, BIGINT)`, and `jsonConcat(ANY, ANY)`.
- Aligned boolean stringification across Python fallback and native C++ public VARCHAR-returning helper surfaces.
- Preserved the existing public null contract: `jsonConcat(NULL, NULL)` returns SQL `NULL`, while non-null list/scalar inputs concatenate as VARCHAR-list output.
- Added parity coverage for integer, decimal/double, boolean, string, null, and multi-item error behavior across forced Python fallback, native-loaded C++ registration, and no-Python/browser-style C++ execution.

## Validation Run During Review

- Review reproducer remediation cluster: `65 passed`.
- Native C++ CQL unit suite: `768 assertions in 2 test cases`.
- Official conformance: ViewDefinition `134/134`, FHIRPath `935/935`, CQL `1706/1706`, DQM `47/47`, overall `2822/2822`.
- Full pytest: `7228 passed, 5 skipped, 9 warnings`.
- Targeted `git diff --check` over the remediated C++/Python/test paths: clean.

## Review Status

Review-40 is resolved. REV-001 is fixed and verified with forced Python fallback, native-loaded C++ registration, no-Python/browser-style C++ execution, native C++ unit tests, full official conformance, and full pytest.
