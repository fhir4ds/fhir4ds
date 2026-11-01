# Engineer Handoff — CQL-17 SKEPTIC iteration 1 (2026-08-22)

All three QA issues fixed at root cause; no workarounds; Python-only changes
(translator + UDF), no native rebuild required (native was already correct in
each case).

## Fixes

1. QA-001 (HIGH, SPEC_VIOLATION, CQL §19.31) — RESOLVED.
   File: `fhir4ds/cql/translator/expressions/_operators.py`
   (`_translate_union_op`). Interval-typed operands are now ALSO detected via
   `_static_structural_type_name(node).startswith("Interval<")` on the CQL
   AST, so `(null as Interval<T>) union Interval[...]` routes to
   `intervalUnion` (runtime null per §19.31) instead of LIST-union
   `jsonConcat` (which raised duckdb BinderException on valid CQL; both-null
   returned `[]` instead of null).
2. QA-002 (MEDIUM, PARITY_VIOLATION, §19.19 Start / §9.15 End) — RESOLVED.
   File: `fhir4ds/cql/duckdb/udf/interval.py` (`_raw_closed_bound`).
   dict/list raw bounds (Quantity interval points) now serialize via
   `orjson.dumps` instead of `str()`, eliminating the invalid-JSON Python
   repr on `start of`/`end of` Quantity intervals. Exact compact-JSON parity
   with the native path.
3. QA-003 (MEDIUM, PARITY_VIOLATION, §19.25 Width) — RESOLVED.
   File: `fhir4ds/cql/duckdb/udf/interval.py` (`intervalWidth` quantity
   branch). Adds `"system":"http://unitsofmeasure.org"` (mirroring
   `interval_size` and native `format_quantity_json`).

## Regression coverage

`fhir4ds/cql/duckdb/tests/integration/test_interval_part3_parity.py`:
- `UnionNullLeft` / `UnionNullRight2` / `UnionNullBoth` defines → null on
  all 3 engines (translated SQL test).
- `StartOfQty` / `EndOfQty` defines → exact JSON quantity points on all
  3 engines.
- Direct-UDF `json_extract_string(intervalWidth(...), '$.system')` → UCUM
  system on all 3 engines.
Focused suites: test_interval_part3_parity.py 7/7; test_interval_udfs.py +
test_v2_expressions.py 204/204.

## Conformance gate (final tree state)

Master gate `conformance/scripts/run_all.py` — see architect handoff /
report for final counts (DQM run against final tree per GATE DISCIPLINE).
Extension binary md5 (unchanged; Python-only fixes):
87e4f6e866bfbc7151eb42ff779c9fd1 across repo bundle
(fhir4ds/cql/duckdb/extensions/cql.duckdb_extension) and site-packages
(~/.local/lib/python3.10/site-packages/...).
