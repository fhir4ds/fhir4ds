# QA Handoff - CQL-08 EXPLORER

Personality: EXPLORER
Phase: QA

## Spec Basis

Verified against the official CQL 1.5.3 Appendix B Nullological Operators page:
- `Coalesce<T>` supports scalar overloads with 2, 3, 4, or 5 arguments and a single `List<T>` overload. The first non-null value is returned; all-null returns null.
- `is null(argument Any)` returns true only when the argument evaluates to null.
- `is true(argument Boolean)` and `is false(argument Boolean)` return true only when the Boolean argument is exactly true or false; otherwise false.

Source: https://cql.hl7.org/09-b-cqlreference.html#nullological-operators

## Probes Run

Created `.temp/qa/cql08_explorer_probe.py`, `.temp/qa/cql08_explorer_probe2.py`, and `.temp/qa/cql08_explorer_probe3.py` to compare translated CQL, native-loaded DuckDB registration, and forced Python fallback registration.

Covered:
- Mixed static scalar operands.
- Function-call form `IsTrue()` / `IsFalse()` versus infix `is true` / `is false`.
- Coalesce scalar arities, empty list, and list overload.
- Native-loaded and forced Python fallback DuckDB execution parity.

## Findings

### QA-001 - Infix `is true` / `is false` uses SQL truthiness

Reproducer:

```cql
define NumIsTrue: 1 is true
define ZeroIsFalse: 0 is false
define StrIsTrue: 'true' is true
```

Actual translated SQL:

```sql
1 IS TRUE
0 IS FALSE
'true' IS TRUE
```

Native-loaded and forced Python fallback DuckDB both returned `true` for all three cases. Direct public helpers already behave correctly: `IsTrue(1)` and `IsFalse(0)` return `false`.

Expected: `is true` / `is false` must share Boolean-only CQL semantics with the public helpers and must not inherit DuckDB numeric/string truthiness.

### QA-002 - Invalid `Coalesce` scalar arities are accepted

Reproducer:

```cql
define Empty: Coalesce()
define OneScalar: Coalesce(1)
define SixScalar: Coalesce(null, null, null, null, null, 1)
```

Actual translation:

```sql
NULL
COALESCE(1)
COALESCE(NULL, NULL, NULL, NULL, NULL, 1)
```

Expected: translator should reject scalar `Coalesce` calls with 0, 1, or more than 5 arguments. The single-list overload remains valid, including empty/all-null lists.

## Recommended Remediation

- Lower infix `is true` / `is false` to the registered CQL helper macros `IsTrue(expr)` / `IsFalse(expr)`.
- Consider `is not true` / `is not false` while touching this code path; if retained, implement as `NOT IsTrue(expr)` / `NOT IsFalse(expr)` rather than SQL truthiness.
- Add Coalesce arity validation in `_translate_coalesce()` before SQL lowering.
- Add regression tests to `fhir4ds/cql/duckdb/tests/integration/test_nullological_parity.py` covering translated execution on both native-loaded and forced Python fallback connections.
