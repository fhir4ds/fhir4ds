# QA Handoff - Iteration 2 (ARCHAEOLOGIST)

**Date**: 2026-05-07
**Personality**: ARCHAEOLOGIST (Memory Safety & Legacy Code Excavator)
**Scope**: Error swallowing, type coercion, dead code paths, C++ extension fallback, reactive.py, CQL interval operators, ViewDef source_table filter, DQM parser hardening

## Summary

Ran 52 targeted tests across 8 excavation areas. Found **0 new runtime bugs** and documented **5 architectural observations / latent risks**. The full test suite passes (6624 passed, 116 skipped, 18 xfailed, 2 xpassed). The iteration-1 bugs (QA-001, QA-002) have been fixed.

## Regression Check

```
pytest fhir4ds/ -x: 6624 passed, 116 skipped, 18 xfailed, 2 xpassed, 138 warnings
Runtime: 60.42s
```

No regressions detected. All previously identified bugs remain fixed.

## Findings

### ARCH-001: _SafeConnection Proxy Exception Gap (MEDIUM - Latent Risk)

**File**: `/mnt/d/fhir4ds/fhir4ds/cql/duckdb/extension.py` lines 100-110
**Evidence**: The `_SafeConnection` proxy catches `duckdb.CatalogException` and `duckdb.InvalidInputException` when a Python UDF name conflicts with a C++ function. However, when a Python UDF is re-registered with the same name (Python-on-Python duplicate), DuckDB raises `duckdb.NotImplementedException`, which is NOT caught by the proxy.

```python
class _SafeConnection:
    def create_function(self, name, *args, **kwargs):
        try:
            return self._real.create_function(name, *args, **kwargs)
        except (duckdb.CatalogException, duckdb.InvalidInputException):
            _logger.debug("Skipping Python UDF %s (C++ conflict)", name)
```

**Mitigating factor**: The outer registration loop in `_register_python_supplements()` wraps each UDF group in `except Exception as e`, which catches `NotImplementedException`. Additionally, the idempotency guard (line 184) prevents double-registration in the first place.

**Impact**: Low in practice. The code path is protected by multiple layers. However, if the idempotency guard is ever removed or bypassed, the `_SafeConnection` proxy alone would not prevent `NotImplementedException` from bubbling up.

---

### ARCH-002: source_table Parameter Not Validated (LOW - Design Note)

**File**: `/mnt/d/fhir4ds/fhir4ds/viewdef/generator.py` lines 109-127
**Evidence**: The `source_table` parameter to `SQLGenerator.__init__()` is used directly in SQL `FROM` clauses without validation. While the `_get_table_name()` method validates the resource type with `_VALID_RESOURCE_TYPE_RE`, the `source_table` value itself is injected raw:

```python
from_sql = f"FROM {table_name} {self.table_alias}"
```

If `source_table` were `"resources; DROP TABLE patients--"`, the SQL would contain this injection string.

**Mitigating factor**: `source_table` is a code-level parameter set by the caller, not parsed from user JSON input. The ViewDefinition JSON parser does not expose `source_table` -- it is always set programmatically.

**Impact**: No direct exploit path from user input. This is a defense-in-depth observation: adding identifier validation (similar to `_SAFE_IDENTIFIER_RE` used for column names) would be prudent.

---

### ARCH-003: Error Swallowing in UDF Registration Loop (LOW - Design Note)

**File**: `/mnt/d/fhir4ds/fhir4ds/cql/duckdb/extension.py` lines 137-140
**Evidence**: The UDF group registration loop catches `Exception` and logs a warning:

```python
for fn, label in [...]:
    try:
        fn(reg_con)
    except Exception as e:
        _logger.warning("UDF group '%s' registration failed: %s", label, e)
```

This means if any UDF group fails to register (e.g., due to a missing dependency or type error), the failure is logged as a warning but execution continues. Downstream queries that use functions from the failed group will raise `CatalogException` at query time, not at registration time.

**Impact**: Delayed error reporting. In production, this could make debugging harder because the root cause (registration failure) is separated in time from the symptom (query failure).

---

### ARCH-004: Interval Quantity JSON Width Returns String Not JSON (LOW - Design Note)

**File**: `/mnt/d/fhir4ds/fhir4ds/cql/duckdb/udf/interval.py` lines 510-516
**Evidence**: When `intervalWidth()` encounters a quantity-valued interval bound, it returns a JSON string:

```python
return _json.dumps({"value": width_val, "unit": unit, "code": unit})
```

But for numeric intervals, it returns a plain string:

```python
return str(result)  # e.g., "10"
```

This inconsistency means callers must try JSON parsing before falling back to numeric parsing.

**Impact**: Minor. The DuckDB SQL layer handles both cases via implicit casts.

---

### ARCH-005: FHIRPath Vectorized UDF Has No Scalar Guard (LOW - Documentation)

**File**: `/mnt/d/fhir4ds/fhir4ds/fhirpath/duckdb/udf.py` lines 207-210
**Evidence**: `fhirpath_udf()` takes `pa.Array` (PyArrow) arguments and calls `.to_pylist()` on them. If called with `None` or a plain string, it raises `AttributeError`:

```
AttributeError: 'NoneType' object has no attribute 'to_pylist'
```

This is NOT a bug -- the function is only called by DuckDB internally with Arrow arrays. But it means the function cannot be safely called from Python for testing. The scalar versions (`fhirpath_text_udf`, `fhirpath_json_udf`, etc.) should be used instead.

**Impact**: Documentation only. Developers writing tests may be confused by this API contract.

---

## Hypothesis Results

| Hypothesis | Result | Detail |
|:---|:---|:---|
| H1: _SafeConnection silently eats non-C++ errors | PARTIALLY CONFIRMED | Catches CatalogException/InvalidInputException but NOT NotImplementedException. Protected by outer exception handler. |
| H2: Interval type coercion misparses years as ints | DISPROVED | `_parse_interval_bound("2024")` correctly returns `date(2024,1,1)`. Date parsing runs before numeric parsing. |
| H3: Error swallowing in DQM evaluator masks real failures | DISPROVED | Evaluator has careful exception hierarchy: (DQMError, KeyboardInterrupt) re-raised, specific errors wrapped in DQMError, unknown errors re-raised. |
| H4: FHIRPath UDF None cascading corrupts downstream | DISPROVED | All UDFs correctly return None for None inputs. DuckDB propagates NULL correctly in SQL. |
| H5: DQM parser silently drops misconfigured populations | CONFIRMED (by design) | Unknown population codes and empty CQL expressions are dropped with warnings. This is documented and intentional. |
| H6: source_table enables SQL injection | DISPROVED for user input | `source_table` is code-level only, not user-controlled. Resource type is validated. |
| H7: Quantity division by zero crashes | DISPROVED | `quantityDivide` correctly returns None when magnitude is 0. |
| H8: C++ extension fallback produces different results | NOT TESTABLE | No C++ extension binary is present in this build. The Python UDF fallback path works correctly. |

## Test Coverage by Area

| Area | Tests | Status |
|:---|:---|:---|
| _SafeConnection proxy | 2 | PASS |
| Interval type coercion | 15 | PASS |
| Interval contains edge cases | 5 | PASS |
| FHIRPath UDF None cascading | 7 | PASS |
| DQM parser edge cases | 7 | PASS |
| ViewDef source_table filter | 4 | PASS |
| Quantity UDF edge cases | 5 | PASS |
| Interval width/size | 5 | PASS |
| **Total** | **52** | **52 PASS** |

## Dead Code Paths Examined

1. **`reactive.py` ReactiveEvaluator**: Fixed in iteration 1. The `update()` method now correctly calls `dqm.MeasureEvaluator(self._con).evaluate()` with proper arguments. Code path was previously dead due to broken API call.

2. **`extension.py` C++ extension loading**: The `_try_load_bundled_cpp_extension()` function has a DuckDB version gate (`1.5.x`). When the version does not match, it logs and falls back cleanly. No C++ binary exists in this environment, so this path is exercised in fallback mode only.

3. **`interval.py` Python repr parsing**: `_parse_interval()` has a fallback to `ast.literal_eval()` for Python repr strings with single quotes. This path is correctly exercised and returns proper results.

4. **`extension.py` idempotency guard**: Lines 183-191 check if CQL UDFs are already registered by executing `SELECT AgeInYears(NULL)`. If this succeeds, registration is skipped. This prevents double-registration when `register()` is called multiple times on the same connection.

## Files Examined

### Recently Changed (Primary Focus)
- `/mnt/d/fhir4ds/fhir4ds/dqm/reactive.py` - ReactiveEvaluator (fixed in iter 1)
- `/mnt/d/fhir4ds/fhir4ds/cql/duckdb/udf/interval.py` - Interval operators, precision comparisons
- `/mnt/d/fhir4ds/fhir4ds/viewdef/generator.py` - SQL generator, source_table filter
- `/mnt/d/fhir4ds/fhir4ds/dqm/parser.py` - Measure parser
- `/mnt/d/fhir4ds/fhir4ds/cql/parser/parser.py` - Parser hardening (recursion limit fix)

### Error Swallowing (Secondary Focus)
- `/mnt/d/fhir4ds/fhir4ds/cql/duckdb/extension.py` - _SafeConnection proxy, UDF registration
- `/mnt/d/fhir4ds/fhir4ds/fhirpath/duckdb/udf.py` - FHIRPath UDFs, None handling
- `/mnt/d/fhir4ds/fhir4ds/cql/duckdb/udf/quantity.py` - Quantity arithmetic
- `/mnt/d/fhir4ds/fhir4ds/cql/duckdb/udf/datetime.py` - DateTime interval unwrap
- `/mnt/d/fhir4ds/fhir4ds/dqm/evaluator.py` - Measure evaluation orchestration

### Error-Prone Patterns Audited
- 97 instances of `except Exception` across the codebase
- 21 instances of bare `except Exception: pass` or `except Exception: return None`
- 0 instances of bare `except:` (no exception type)
- All error-swallowing patterns are intentional (cleanup, validation, fallback)

## Test Files

- `/mnt/d/fhir4ds/.temp/qa/test_qa_archaeologist.py` - Iteration 2 QA tests (52 tests)
