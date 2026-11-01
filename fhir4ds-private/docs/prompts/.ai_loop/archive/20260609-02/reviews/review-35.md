# Code Review Findings

Spec compliance milestone review after 35 completed chunks. Findings are ordered by severity.

## Findings

### REV-001 - MEDIUM - RESOLVED - `intervalEquals` diverges between Python/native-loaded and C++ no-Python surfaces for one-sided unbounded intervals

`fhir4ds/cql/duckdb/udf/interval.py:1577` treats matching missing bounds as indeterminate when `nulls_equivalent=False`, so `intervalEquals()` returns SQL NULL whenever either effective start or end is `None`. The C++ no-Python implementation calls `Interval::operator==` from `extensions/cql/src/cql_extension.cpp:1243`, and that operator explicitly treats both missing effective starts/ends as equal in `extensions/cql/src/cql/interval.cpp:671`.

Reproducer:

```sql
-- translated CQL: Interval[1, null) = Interval[1, null)
SELECT intervalEquals(
  intervalFromBounds(CAST(1 AS VARCHAR), NULL, TRUE, FALSE),
  intervalFromBounds(CAST(1 AS VARCHAR), NULL, TRUE, FALSE)
);
```

Observed during review:

```text
forced Python fallback: NULL
native-loaded Python-shadowed registration: NULL
no-Python/browser-style C++ surface: TRUE
```

The same divergence occurs for `Interval(null, 5] = Interval(null, 5]`. This is a browser/WASM conformance risk because the normal native-loaded Python registration shadows `intervalEquals`, hiding the C++ behavior from most tests.

Resolution: Python `intervalEquals` now treats matching missing effective bounds as equal and one-missing-vs-present bounds as false, matching the no-Python C++ surface. Added translated and direct parity coverage across forced Python fallback, native-loaded registration, and no-Python/browser-style C++.

### REV-002 - MEDIUM - RESOLVED - malformed Ratio component unit helpers raise in Python fallback but return NULL in C++ no-Python

`ratioNumeratorUnit()` and `ratioDenominatorUnit()` assume the selected component is a dict and call `.get()` unguarded at `fhir4ds/cql/duckdb/udf/ratio.py:90` and `fhir4ds/cql/duckdb/udf/ratio.py:99`. Malformed internal Ratio JSON with a scalar component raises `AttributeError`, aborting the row/query in Python fallback. The C++ implementation returns SQL NULL for the same malformed shape.

Reproducer:

```sql
SELECT ratioNumeratorUnit('{"numerator":5,"denominator":{"value":1}}');
SELECT ratioDenominatorUnit('{"numerator":{"value":5},"denominator":5}');
```

Observed during review:

```text
forced Python fallback: InvalidInputException from AttributeError
no-Python/browser-style C++ surface: NULL
```

This violates the public helper row-resilience pattern used elsewhere for malformed Quantity/Ratio inputs.

Resolution: Python `ratioNumeratorUnit()` and `ratioDenominatorUnit()` now guard malformed scalar components and return SQL NULL, matching C++ row resilience. Added forced Python fallback, native-loaded, and no-Python C++ parity coverage plus Python unit coverage.

## Validation Notes

Used current source, active state files, AGENTS/GLOBAL rules, current tests, and current conformance reports. Did not inspect archived workflow outputs as proof of behavior.

Post-remediation validation:

- Focused parity/unit pytest: `52 passed`.
- Broader interval/public-surface pytest: `119 passed`.
- Full conformance: `2822/2822` (`ViewDefinition 134/134`, `FHIRPath R4 935/935`, `CQL 1706/1706`, `DQM 47/47`).
- Full pytest: `7199 passed, 5 skipped, 9 warnings`.
- Targeted diff check on changed review-remediation files: clean.
