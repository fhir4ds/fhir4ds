# Engineer Handoff: CQL-17 SKEPTIC

Resolved:
- `QA-001` HIGH: `properly included in` now distinguishes a null interval
  value from an existing interval with null bounds. Direct/public
  `intervalProperlyIncludedIn(valid_interval, NULL)` returns SQL NULL across
  forced Python fallback, native-loaded registration, and no-Python C++.
  Translated `Interval[1, 5] properly included in (null as
  Interval<Integer>)` also returns NULL.

Implementation:
- `fhir4ds/cql/duckdb/udf/interval.py`: removed the null-container
  shortcut from `intervalProperlyIncludedIn`.
- `extensions/cql/src/cql_extension.cpp`: native C++ UDF now marks a null
  right interval argument invalid instead of returning `true`.
- `fhir4ds/cql/translator/expressions/_operators.py`: preserves the official
  `Interval[1, 5] properly included in Interval[null, null]` behavior by
  rewriting only that authored interval literal to an existing unbounded
  interval for this operator.
- `fhir4ds/cql/duckdb/tests/integration/test_interval_part3_parity.py` and
  `.temp/qa/cql17_skeptic_probe.py`: added regression coverage for both the
  null interval value and null-bound interval cases.
- Rebuilt and copied `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`.

Validation:
- `.temp/qa/cql17_skeptic_probe.py`: PASS
- CQL-17/no-Python focused pytest: 6/6
- Interval part1/2/3 plus WASM/C++/translate gate: 31/31
- Official CQL interval XML: 412/412
- Full conformance: 2822/2822

No new issues discovered.
