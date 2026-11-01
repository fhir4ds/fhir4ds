# Code Review Findings

Scope: SPEC COMPLIANCE MILESTONE REVIEW after fresh FP-01 through FP-05 passes. Reviewed the changed FHIRPath Python fallback, native C++ extension, and parity tests.

## Findings

### REV-001 - HIGH - Native `fhirpath_json` can emit invalid JSON for escaped Quantity units

Evidence: [fhirpath_extension.cpp](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1434) serializes `FPValue::Type::Quantity` by escaping only `"` and `\` in `val.quantity_unit`. FP-01 added normal string-unescape handling for quoted Quantity units, so valid literals such as `1 'm\ng'`, `1 'm\rg'`, `1 'm\tg'`, and `1 'm\u0001g'` can now place raw control characters into the unit. Native output becomes invalid JSON, while the Python fallback escapes it correctly.

Reproducer:

```sql
SELECT fhirpath_json('{"resourceType":"Patient"}'::JSON, '1 ''m\ng''');
-- native: [{"value":1,"unit":"m
-- g"}]  -- invalid JSON
-- forced Python fallback: [{"value":1,"unit":"m\\ng"}]
```

Proposed safer implementation: reuse the same JSON string escaping branch used for ordinary strings, or centralize a small `escapeJsonString()` helper for all handwritten JSON assembly, including Quantity units.

### REV-002 - HIGH - Native Section 5.1 arity validation still accepts malformed expressions

Evidence: [evaluator.cpp](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1220) treats any non-empty `exists(...)` as a criteria call and ignores extra children. [evaluator.cpp](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:2226) dispatches `all(...)` whenever at least one child exists, again ignoring extra children and allowing missing criteria to fall through as valid empty output. Several no-arg Section 5.1 functions also return results before checking `node.children`.

Observed native/fallback divergence:

```text
id.exists(true, false): native fhirpath_is_valid=true, native result=['true'], fallback valid=false
id.all(): native fhirpath_is_valid=true, native result=[], fallback valid=false
id.empty(1): native fhirpath_is_valid=true, native result=['false'], fallback valid=false
id.count(1): native fhirpath_is_valid=true, native result=['1'], fallback valid=false
id.subsetOf(id, id): native fhirpath_is_valid=true, native result=['true'], fallback valid=false
```

Proposed safer implementation: add exact arity checks for all Section 5.1 functions before semantic evaluation: `exists` allows 0 or 1, `all` requires 1, `subsetOf`/`supersetOf` require 1, and `empty`/`count`/`distinct`/`isDistinct`/Boolean aggregate functions require 0. Add native sqllogictest and forced fallback parity coverage.

### REV-003 - MEDIUM - Native `fhirpath_timestamp` accepts invalid resource-backed DateTime strings

Evidence: [fhirpath_extension.cpp](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1501) added `IsDateTimeText()`, but it validates only lexical separators and digit positions. It does not reject year `0000`, invalid months/days, invalid clock fields, or invalid timezone ranges before [IsTimestampValue](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1604) accepts JSON string results as timestamps. The Python fallback uses `FP_DateTime(...)` at [udf.py](/mnt/d/fhir4ds/fhir4ds/fhirpath/duckdb/udf.py:1360), which rejects these cases.

Observed native/fallback divergence:

```text
{"v":"2024-13T"} / fhirpath_timestamp(v): native="2024-13T", fallback=NULL
{"v":"0000-01-01T00:00:00"} / fhirpath_timestamp(v): native returns the string, fallback=NULL
{"v":"2024-01-01T00:00:00+99:99"} / fhirpath_timestamp(v): native returns the string, fallback=NULL
```

Proposed safer implementation: route string timestamp validation through the same semantic date/time parser used by native literal evaluation, or extend `IsDateTimeText()` to enforce the same range and precision rules as `parseDateTimeParts()`.

### REV-004 - MEDIUM - `fhirpath_quantity` accepts shape-only invalid Quantity objects

Evidence: native [IsQuantityValue](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1618) and Python fallback [fhirpath_quantity_udf](/mnt/d/fhir4ds/fhir4ds/fhirpath/duckdb/udf.py:1400) accept any object with `value` plus `code` or `unit`. They do not require `value` to be numeric/finite or `unit`/`code` to be string-like. This lets invalid data pass through a typed wrapper that is supposed to return Quantity values only.

Reproducer:

```sql
SELECT fhirpath_quantity('{"resourceType":"Observation","v":{"value":"abc","unit":"mg"}}'::JSON, 'v');
-- native and fallback both return {"value":"abc","unit":"mg"}
```

Proposed safer implementation: validate Quantity object shape before returning it: numeric finite `value`, string `unit` or `code`, and row-resilient NULL for malformed shapes. Add native/fallback parity tests for malformed Quantity JSON.

## Review Notes

No SQL string interpolation or source-adapter credential handling changes were found in the FP-01 through FP-05 delta. The main risks are public UDF contract drift, malformed JSON output, and missing native arity guard tests for Section 5.1.
