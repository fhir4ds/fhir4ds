# Code Review Findings

Scope: SPEC COMPLIANCE MILESTONE REVIEW after fresh FP-01 through FP-10 passes. Reviewed the FHIRPath Python fallback, native C++ extension, bundled extension behavior, and recent parity tests, with emphasis on review-05 risks plus FP-06 through FP-10 conversion/string/regex/Unicode changes.

## Findings

### REV-001 - HIGH - Native Section 5.1 arity validation still accepts malformed calls

Evidence: [evaluator.cpp](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1343) adds exact arity guards for many FP-05 through FP-10 functions, but Section 5.1 helpers are not guarded before dispatch. [count/empty/Boolean aggregate dispatch](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1406), [all dispatch](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:2292), and [subsetOf/supersetOf dispatch](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:2553) ignore missing or extra arguments. `exists(criteria)` also uses only the first child at [evalExists](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1242).

Reproduced on the current bundled native extension:

```text
id.exists(true, false) => (['true'], '[true]', true)
id.all()               => ([], null, true)
id.empty(1)            => (['false'], '[false]', true)
id.count(1)            => (['1'], '[1]', true)
id.subsetOf(id, id)    => (['true'], '[true]', true)
bools.allTrue(1)       => (['true'], '[true]', true)
missing.isDistinct(1)  => (['true'], '[true]', true)
```

Forced Python fallback returns empty/NULL with `fhirpath_is_valid=false` for these malformed signatures. Add exact arity checks for all Section 5.1 functions before semantic evaluation: `exists` allows 0 or 1 argument, `all` requires 1, `subsetOf`/`supersetOf` require 1, and `empty`/`count`/`distinct`/`isDistinct`/Boolean aggregates/`hasValue`/`not` require 0.

### REV-002 - MEDIUM - Native `fhirpath_timestamp` accepts invalid resource-backed DateTime strings

Evidence: [IsDateTimeText](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1511) checks only separators and digit positions before [IsTimestampValue](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1614) accepts JSON strings as timestamps. It does not reject year `0000`, invalid month/day/time ranges, or invalid timezone offsets. Python fallback validates through `FP_DateTime` at [udf.py](/mnt/d/fhir4ds/fhir4ds/fhirpath/duckdb/udf.py:1784).

Reproduced:

```text
{"dt_bad":"2024-13T"} / fhirpath_timestamp(dt_bad) => native "2024-13T", fallback NULL
{"dt_zero":"0000-01-01T00:00:00"} => native returns the string, fallback NULL
{"dt_tz":"2024-01-01T00:00:00+99:99"} => native returns the string, fallback NULL
```

Route resource-backed string validation through the same semantic DateTime parser used for literal/conversion validation, or make `IsDateTimeText()` enforce identical range and timezone rules.

### REV-003 - MEDIUM - `fhirpath_quantity` accepts malformed Quantity objects

Evidence: native [IsQuantityValue](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1628) and fallback [fhirpath_quantity_udf](/mnt/d/fhir4ds/fhir4ds/fhirpath/duckdb/udf.py:1826) accept any object with `value` plus `code` or `unit`. They do not require a finite numeric `value`, or string-like `code`/`unit`, before returning through a typed Quantity wrapper.

Reproduced on both native and fallback:

```sql
SELECT fhirpath_quantity(
  '{"resourceType":"Observation","v":{"value":"abc","unit":"mg"}}'::JSON,
  'v'
);
-- {"value":"abc","unit":"mg"}
```

The FP-08 conversion surfaces now reject malformed Quantity objects, but this typed wrapper still leaks invalid shape. Reuse the strict Quantity materialization helper here and return row-resilient NULL for malformed objects.

### REV-004 - MEDIUM - Native Unicode `upper()` / `lower()` remains incomplete after FP-10

Evidence: native case conversion is still a hand-maintained code-point table in [fn_upper](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:3061) and [fn_lower](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:3150). FP-10 added several Turkish/Greek/Latin pairs, but valid Unicode case mappings outside the table still diverge from the forced Python fallback.

Reproduced:

```text
'ǆ'.upper() => native ['ǆ'], fallback ['Ǆ']
'Ǆ'.lower() => native ['Ǆ'], fallback ['ǆ']
'ſ'.upper() => native ['ſ'], fallback ['S']
'ẞ'.lower() => native ['ẞ'], fallback ['ß']
'ﬃ'.upper() => native ['ﬃ'], fallback ['FFI']
```

This is not just a missing test for a single character; the local table will keep producing backend drift as new scripts appear in patient names, identifiers, and text. Replace the table with a generated Unicode case map or a Unicode-aware library path, then keep focused native/fallback tests for non-ASCII expansion and one-to-many mappings.

## Review Notes

Review-05 `fhirpath_json` Quantity unit escaping no longer reproduces; current native `fhirpath_json` escapes control characters in Quantity units. The bundled Linux extension hash matches the current release build hash. No new SQL interpolation issue was found in the FP-01 through FP-10 delta.
