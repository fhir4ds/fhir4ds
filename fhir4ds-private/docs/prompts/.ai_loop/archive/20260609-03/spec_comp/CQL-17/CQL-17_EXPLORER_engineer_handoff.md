# Engineer Handoff: CQL-17 EXPLORER

Resolved:
- `QA-001` HIGH: malformed non-null public `expand` / `expand_points` `per` Quantity JSON now returns SQL NULL instead of silently defaulting.

Root cause:
- Python `_parse_expand_per()` collapsed invalid supplied values into the same `(None, None)` result as omitted `per`.
- C++ `ParseExpandStep()` returned an unsupplied default step when Quantity parsing failed; the list overload also converted invalid per into an empty expansion.

Fix:
- Python `expand` now distinguishes omitted SQL NULL `per` from supplied invalid `per`; invalid values include malformed JSON, missing/non-numeric `value`, Boolean values, and string values.
- C++ `ExpandStep` now carries a `valid` flag; invalid supplied `per` nulls both point and list expansion paths.
- Added regression coverage to `test_interval_part3_parity.py`.
- Rebuilt and copied `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`.

Validation:
- `.temp/qa/cql17_explorer_probe.py`: PASS.
- `test_interval_part3_parity.py`: 3/3.
- Interval part 1/2/3 plus WASM/no-Python gates: 31/31.
- Official interval operators: 412/412.
- Full conformance: 2822/2822.
