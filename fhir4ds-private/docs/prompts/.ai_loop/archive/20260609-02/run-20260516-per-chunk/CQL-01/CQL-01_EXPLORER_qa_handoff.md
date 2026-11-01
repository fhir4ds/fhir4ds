# CQL-01 EXPLORER QA Handoff

## Scope

CQL primitive types: Any, Boolean, Integer, Decimal, String, and Long. This pass tested translator behavior, DuckDB SQL execution, direct CQL DuckDB macro/UDF surfaces, parser boundaries, and native-loaded versus forced Python fallback parity from fresh probes.

## Findings

### CQL01-EXP-001 - RESOLVED - HIGH

Direct FHIR choice primitive assertions used SQL text shape instead of runtime FHIR primitive type. Fresh native-loaded and forced Python fallback probes showed `valueString: "5"` satisfying `as Integer`, `valueInteger` satisfying `as String`, and `valueInteger is Integer` returning false.

### CQL01-EXP-002 - RESOLVED - HIGH

Primitive conversions lowered through generic DuckDB casts or direct macros that did not match CQL conversion semantics. `ToInteger()` and `convert ... to Integer` rounded decimal-looking values, while `ToDecimal`/`ToBoolean` invalid-input behavior diverged from conversion-check behavior.

### CQL01-EXP-003 - RESOLVED - MEDIUM

Malformed no-whitespace numeric suffixes such as `1LL`, `1.0L`, and `1day` were accepted instead of rejected by the numeric lexer.

### CQL01-EXP-004 - RESOLVED - MEDIUM

Materialized primitive query definitions lost primitive type metadata. A definition such as `First([Observation] O return O.valueQuantity.value)` was later treated as String instead of Decimal for `is`/`as` checks.

## Validation

- Native-loaded and forced Python fallback primitive parity probes passed for direct FHIR choice values and materialized primitive CTE values.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py -q --tb=short` passed: 7 tests.
- CQL conversion/forced-backend parity subset passed: 7 tests.
- Targeted DQM rerun for CMS771 and CMS0334 passed 2/2 at 100%.
- Official CQL conformance passed 1706/1706.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- Broad CQL unit/integration/DuckDB integration pytest passed 1361 with 5 skips.
- `git diff --check` was clean.
