# Code Review Findings

Scope: SPEC COMPLIANCE MILESTONE REVIEW after fresh FP-01 through FP-20 passes. Reviewed cumulative FHIRPath native C++ and Python fallback changes, the bundled DuckDB extension behavior, FP-16 through FP-20 tests and handoff evidence, and still-open review-15 risks. This was review-only; no fixes were implemented.

## Findings

### REV-001 - HIGH - Native Section 5.1 arity validation still accepts malformed calls

Evidence: [evalExists](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1548) accepts any non-empty argument list and evaluates only `node.children[0]`, so extra arguments are ignored. The central native arity guard block at [evalFunction](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1649) now covers `not`, aggregate, conversion, string, math, and reflection helpers touched through FP-20, but it still omits Section 5.1 helpers including `exists`, `all`, `subsetOf`, `supersetOf`, `count`, `empty`, `distinct`, `isDistinct`, `hasValue`, and Boolean aggregates. Dispatch then executes those helpers without exact signature validation at [count/empty/hasValue/not](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1738), [all](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:2636), and [subsetOf/supersetOf](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:2897).

Fresh native vs forced-fallback probe:

```text
arr.exists(true, false)  native ['true'] / valid true, fallback empty / valid false
arr.all()               native empty / valid true, fallback empty / valid false
arr.all(true, false)    native ['true'] / valid true, fallback empty / valid false
arr.subsetOf(arr, arr)  native ['true'] / valid true, fallback empty / valid false
arr.supersetOf(arr, arr) native ['true'] / valid true, fallback empty / valid false
arr.count(true)         native ['2'] / valid true, fallback empty / valid false
arr.empty(false)        native ['false'] / valid true, fallback empty / valid false
arr.distinct(true)      native ['1','2'] / valid true, fallback empty / valid false
arr.isDistinct(true)    native ['true'] / valid true, fallback empty / valid false
arr.hasValue(true)      native ['false'] / valid true, fallback empty / valid false
```

Proposed safer implementation: add exact arity checks for all Section 5.1 functions before semantic dispatch: `exists` allows 0 or 1 argument, `all` requires 1, `subsetOf`/`supersetOf` require 1, and `empty`/`count`/`distinct`/`isDistinct`/Boolean aggregates/`hasValue` require 0. Keep native sqllogictest and forced fallback parity coverage together.

### REV-002 - MEDIUM - Native `fhirpath_timestamp` still accepts invalid resource-backed DateTime strings

Evidence: native [IsDateTimeText](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1540) checks only digit and separator shape before [IsTimestampValue](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1614) accepts JSON strings as timestamps. It does not enforce year, month, day, hour, minute, second, or timezone ranges before [FhirpathTimestampFunction](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1680) returns the string. The Python fallback validates through `FP_DateTime` and returned NULL for the same values.

Fresh native vs forced-fallback probe:

```text
dt_bad_month = "2024-13-01T00:00:00"       native "2024-13-01T00:00:00", fallback NULL
dt_bad_hour  = "2024-01-01T25:00:00"       native "2024-01-01T25:00:00", fallback NULL
dt_bad_tz    = "2024-01-01T00:00:00+24:00" native "2024-01-01T00:00:00+24:00", fallback NULL
dt_bad_year  = "0000-01-01T00:00:00"       native "0000-01-01T00:00:00", fallback NULL
```

Proposed safer implementation: route resource-backed timestamp wrapper validation through the same strict temporal parser used by literal/conversion paths, or make `IsDateTimeText()` enforce identical calendar, time, and timezone rules.

### REV-003 - MEDIUM - `fhirpath_quantity` typed wrappers accept malformed Quantity objects

Evidence: native [IsQuantityValue](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1628) accepts any JSON object with a `value` key and either `code` or `unit`, then [FhirpathQuantityFunction](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1722) returns the raw object string. It does not reuse the stricter native Quantity materialization path now present in `evaluator.cpp`. The Python fallback has the same shape-only leak at [fhirpath_quantity_udf](/mnt/d/fhir4ds/fhir4ds/fhirpath/duckdb/udf.py:2354), returning `_json_serialize(val)` whenever the dict has `value` plus `code` or `unit`.

Fresh native and forced-fallback results both return malformed objects instead of row-resilient NULL:

```text
{"value":"abc","unit":"mg"} -> {"value":"abc","unit":"mg"}
{"value":"5","unit":"mg"}   -> {"value":"5","unit":"mg"}
{"value":5,"unit":7}        -> {"value":5,"unit":7}
```

Proposed safer implementation: typed Quantity wrappers should require finite JSON-numeric `value` plus string `code` or `unit`, returning NULL for malformed FHIR Quantity shapes. This is separate from `fhirpath_json`, which may still preserve raw JSON values.

### REV-004 - MEDIUM - Native Unicode `upper()` / `lower()` still use an incomplete hand-maintained case table

Evidence: native case conversion remains a local code-point table in [fn_upper](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:3406) and [fn_lower](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:3495). FP-10 added several Turkish, Greek, and Latin Extended-A mappings, but the table still misses common Unicode simple and expansion mappings that the Python fallback handles.

Fresh native vs forced-fallback probe:

```text
lower.upper() for "ǆſﬃ" -> native ["ǆſﬃ"], fallback ["ǄSFFI"]
upper.lower() for "Ǆẞ"  -> native ["Ǆẞ"], fallback ["ǆß"]
```

Proposed safer implementation: replace the local table with generated Unicode case data or a Unicode-aware library path, then keep native/fallback coverage for one-to-one and one-to-many mappings. Treat this as a design problem, not a one-character patch list.

### REV-005 - MEDIUM - Type and choice behavior still embeds FHIR model knowledge in generic runtime code

Evidence: the native evaluator keeps FHIR primitive field metadata in [fhirFieldType](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1171), including the FP-20 surgical addition of `subjectType` as a `code`. It also keeps FHIR type hierarchy and known-type lists in native helpers, infers choice types from local suffix rules, and infers complex types through field-name heuristics in [fn_isType](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:6065). The Python fallback has parallel choice metadata and suffix logic at [_get_choice_type_lookup](/mnt/d/fhir4ds/fhir4ds/fhirpath/duckdb/udf.py:1134) and [_choice_type_suffix](/mnt/d/fhir4ds/fhir4ds/fhirpath/duckdb/udf.py:1364).

This violates the repository rule that FHIR resource/type/choice behavior should come from schema metadata, generated model artifacts, or registries rather than generic runtime branches. FP-20 fixed `Questionnaire.subjectType` correctly for one field, but the fix expanded the hand-maintained map and therefore increased drift risk between native C++, Python fallback, and generated metadata.

Proposed safer implementation: move these tables behind a generated metadata boundary or shared registry, and add drift tests that compare native type resolution against the generated Python FHIR type metadata.

### REV-006 - MEDIUM - String/STU helper arity validation is incomplete in native and fallback wrappers

Evidence: the native arity guard block at [evalFunction](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1649) covers many string functions added in FP-09/FP-10, but omits `trim`, `split`, `join`, `matchesFull`, `escape`, `unescape`, `encode`, and `decode`. Dispatch later evaluates only the first argument, or treats missing arguments as empty-result runtime errors, so invalid calls can be reported as valid and sometimes produce results. The Python fallback scanner also omits these helpers from [_FHIRPATH_STRING_SEARCH_ARITY](/mnt/d/fhir4ds/fhir4ds/fhirpath/duckdb/udf.py:389), so `fhirpath_is_valid()` does not consistently reject malformed signatures.

Fresh probe:

```text
s.trim(1)                 native ["abc"] / valid true, fallback empty / valid true
s.split(",", "x")         native [" abc "] / valid true, fallback empty / valid true
arr.join(",", "x")        native ["a,b"] / valid true, fallback empty / valid false
s.matchesFull("a", "b")   native [false] / valid true, fallback empty / valid true
s.escape("html", "x")     native [" abc "] / valid true, fallback empty / valid true
s.unescape("html", "x")   native [" abc "] / valid true, fallback empty / valid true
s.encode()                native empty / valid true, fallback empty / valid false
s.decode("url", "x")      native empty / valid true, fallback empty / valid false
```

Proposed safer implementation: define exact signatures for these helper surfaces in both native and fallback pre-validation, then add parity tests that assert public result UDF row resilience and `fhirpath_is_valid=false` for malformed call shapes.

## Review Notes

Focused review probes were run against the current bundled native extension and a forced Python fallback connection. Full conformance was not rerun during this review-only pass; FP-20 EXPLORER reported the latest full baseline as 2822/2822.
