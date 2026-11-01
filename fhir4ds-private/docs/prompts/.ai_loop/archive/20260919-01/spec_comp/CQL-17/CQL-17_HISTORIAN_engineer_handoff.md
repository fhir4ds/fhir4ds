# Engineer Handoff — CQL-17 HISTORIAN (2nd launch) iteration 1 (2026-08-22)

All 4 QA issues fixed at root cause; no workarounds; no silent fallbacks.
Changes span the CQL translator (Python), the Python interval UDFs, and the
native C++ extension (rebuilt + redeployed).

## Fixes

1. QA-001 (HIGH, SPEC_VIOLATION, §19.27) + QA-002 (HIGH, §19.28/§19.29) —
   RESOLVED. Files:
   `fhir4ds/cql/translator/expressions/_temporal_comparisons.py`,
   `fhir4ds/cql/translator/expressions/_operators.py` (pass `expr`).
   New `_numeric_interval_point_kind(expr)` statically classifies interval
   point type from the CQL AST (`_static_structural_type_name` +
   literal-bound peek for `Interval<Any>` mixed literals). When the point
   kind is numeric (Integer/Long/Decimal incl. mixed) or Quantity, the
   no-precision interval `same as` / `same or after` / `same or before`
   lower to DECIMAL casts (`=`, `>=`, `<=`) or `quantityCompare` — never to
   cqlDateTimeEqual/cqlSameOr*. Temporal operands keep the temporal path
   (Date/DateTime/Time and unknown types unchanged; typed-null operands
   propagate null through intervalStart/End).
2. QA-003 (MEDIUM, PARITY_VIOLATION, §19.25/§19.18 + §2) — RESOLVED.
   `extensions/cql/src/cql/interval.cpp`: static `NumericBoundValue` helper;
   width_string/size_string Integer and Decimal branches now fall back to
   cross-type numeric computation when only one bound carries int_val/dec_val
   (mixed Integer/Decimal intervals). Exact uint64/__int128 integer paths
   preserved for same-type bounds.
3. QA-004 (MEDIUM, PARITY_VIOLATION, canonical Quantity JSON) — RESOLVED.
   Native `quantity_json_for_bound` canonicalizes via
   `parse_quantity_json` + `format_quantity_json` (value/unit/code/system).
   Python lockstep: `_canonicalize_quantity_bound` helper in
   `fhir4ds/cql/duckdb/udf/interval.py`, applied in `_raw_closed_bound`
   (start/end) and in `pointFrom` (Quantity points), with float value
   normalization to match native yyjson real output.

## Extension rebuild + deploy

Incremental `cmake --build build/release` (Unix Makefiles tree).
Deployed md5 **3e7d4167143e01907fdd8561db43b7d7** to BOTH
`fhir4ds/cql/duckdb/extensions/cql.duckdb_extension` (repo bundle) and
`~/.local/lib/python3.10/site-packages/fhir4ds/cql/duckdb/extensions/`
(site-packages); no ~/.duckdb cache present. Re-verified through fresh
no-Python connections.

NOTE (pre-existing, NOT from this launch): native unittest
`test/sql/cql.test:110` `cqlDurationBetween('2012-01-02','2012','month')`
returns end 10 vs expected 11 — verified failing on a build with this
launch's patch reverted (working-tree state from prior sessions). Logged to
AGENTS.md for follow-up; not part of the master gate baseline.

## Regression coverage

`test_interval_part3_parity.py` (now 10 tests): new
- `..._historian2_numeric_same_family_per_spec` — 14 defines × 3 engines
  (Decimal/mixed/Integer/Quantity same-as + same-or-after/before, null
  operands, and Date intervals still routing through temporal UDFs).
- `..._historian2_mixed_width_size_per_spec` — mixed bounds width/size × 3.
- `..._historian2_quantity_bound_json_canonical` — start/end/point-from
  Quantity canonical JSON × 3.
- StartOfQty/EndOfQty expectations updated to canonical shape.

Focused suites: test_interval_part3_parity.py 10/10;
test_interval_udfs.py + test_v2_expressions.py 204/204.

Master gate: run against FINAL tree state — see architect handoff for
counts (DQM included per GATE DISCIPLINE, single pass, no ERRORs so no
retry needed).
