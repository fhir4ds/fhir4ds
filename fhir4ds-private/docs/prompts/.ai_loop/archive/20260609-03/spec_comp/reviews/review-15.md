# Code Review Findings

Scope: SPEC COMPLIANCE MILESTONE REVIEW after fresh FP-01 through FP-15 passes. Reviewed the FHIRPath Python fallback, native C++ extension source, bundled extension behavior, FP-01 through FP-15 archived handoffs, and recent parity tests, with emphasis on Section 5.1 through Section 6.3 changes, typed DuckDB wrapper boundaries, native-vs-Python fallback drift, and model-knowledge architecture rules.

## Findings

### REV-001 - HIGH - Native Section 5.1 arity validation still accepts malformed calls

Evidence: [evalExists](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1548) accepts any non-empty argument list and evaluates only `node.children[0]`, so `arr.exists(true, false)` ignores the second argument. The central native arity guard block at [evalFunction](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1649) covers many later FP-05 through FP-15 functions but still omits Section 5.1 helpers such as `count`, `empty`, `distinct`, `isDistinct`, `hasValue`, `not`, `all`, `subsetOf`, and `supersetOf`. Dispatch then executes those helpers without exact signature validation at [count/empty/hasValue/not](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1729), [all](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:2624), and [subsetOf/supersetOf](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:2885).

Fresh probe against the current bundled native extension:

```text
exists(true, false)        => native fhirpath_is_valid true, fallback false
arr.exists(true, false)    => native ['true'] / true, fallback empty / false
all()                      => native fhirpath_is_valid true, fallback false
arr.all(true, false)       => native ['true'] / true, fallback empty / false
empty(1)                   => native ['false'] / true, fallback empty / false
count(1)                   => native ['1'] / true, fallback empty / false
distinct(1)                => native returns the input resource / true, fallback empty / false
isDistinct(1)              => native ['true'] / true, fallback empty / false
subsetOf(arr, arr)         => native ['false'] / true, fallback empty / false
supersetOf(arr, arr)       => native ['false'] / true, fallback empty / false
```

Add exact arity checks for all Section 5.1 functions before semantic dispatch: `exists` allows 0 or 1 argument, `all` requires 1, `subsetOf`/`supersetOf` require 1, and `empty`/`count`/`distinct`/`isDistinct`/Boolean aggregates/`hasValue`/`not` require 0.

### REV-002 - MEDIUM - Native `fhirpath_timestamp` still accepts invalid resource-backed DateTime strings

Evidence: native [IsDateTimeText](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1511) checks only separator positions and digit shapes before [IsTimestampValue](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1614) accepts JSON strings as timestamps. It does not enforce year, month, day, hour, minute, second, or timezone ranges before [FhirpathTimestampFunction](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1680) returns the string. The Python fallback wrapper validates through `FP_DateTime` at [udf.py](/mnt/d/fhir4ds/fhir4ds/fhirpath/duckdb/udf.py:1883) and returned NULL for the same invalid strings in a fresh forced-fallback connection.

Fresh native results:

```text
{"dt":"2024-13-01T00:00:00"}       / fhirpath_timestamp(dt) => "2024-13-01T00:00:00"
{"dt":"2024-01-01T25:00:00"}       / fhirpath_timestamp(dt) => "2024-01-01T25:00:00"
{"dt":"2024-01-01T00:00:00+24:00"} / fhirpath_timestamp(dt) => "2024-01-01T00:00:00+24:00"
{"dt":"0000-01-01T00:00:00"}       / fhirpath_timestamp(dt) => "0000-01-01T00:00:00"
```

Route resource-backed timestamp wrapper validation through the same strict temporal parser used by literal/conversion paths, or make `IsDateTimeText()` enforce identical calendar/time/timezone rules.

### REV-003 - MEDIUM - `fhirpath_quantity` typed wrappers accept malformed Quantity objects

Evidence: native [IsQuantityValue](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1628) accepts any JSON object with a `value` key and either `code` or `unit`, then [FhirpathQuantityFunction](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1722) returns the raw string. It does not reuse the stricter native Quantity materialization path at [tryJsonToQuantity](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1013). The Python fallback has the same shape-only leak at [fhirpath_quantity_udf](/mnt/d/fhir4ds/fhir4ds/fhirpath/duckdb/udf.py:1923), returning `_json_serialize(val)` whenever the dict has `value` plus `code` or `unit`.

Fresh native and forced-fallback results both return malformed objects instead of row-resilient NULL:

```text
{"q":{"value":"abc","unit":"mg","system":"http://unitsofmeasure.org"}} => {"value":"abc","unit":"mg","system":"http://unitsofmeasure.org"}
{"q":{"value":"5","unit":"mg","system":"http://unitsofmeasure.org"}}   => {"value":"5","unit":"mg","system":"http://unitsofmeasure.org"}
{"q":{"value":5,"unit":123,"system":"http://unitsofmeasure.org"}}       => {"value":5,"unit":123,"system":"http://unitsofmeasure.org"}
```

Typed Quantity wrappers should require finite JSON-numeric `value` and string `code` or `unit`, then return NULL for malformed FHIR Quantity shapes. This is separate from `fhirpath_json`, which may still preserve raw JSON values.

### REV-004 - MEDIUM - Native Unicode `upper()` / `lower()` still use an incomplete hand-maintained case table

Evidence: native case conversion remains a local code-point table in [fn_upper](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:3393) and [fn_lower](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:3482). FP-10 added several Turkish, Greek, and Latin Extended-A pairs, but the table still misses common Unicode simple and expansion mappings that Python fallback handles.

Fresh native vs forced-fallback probe:

```text
lower.upper() for "ǆſﬃ" => native ["ǆſﬃ"], fallback ["ǄSFFI"]
upper.lower() for "Ǆẞ"  => native ["Ǆẞ"],  fallback ["ǆß"]
```

This remains a design problem, not a one-character patch list. Replace the local table with generated Unicode case data or a Unicode-aware library path, then keep native/fallback coverage for one-to-one and one-to-many mappings.

### REV-005 - MEDIUM - Type and choice behavior still embeds FHIR model knowledge in generic runtime code

Evidence: the native evaluator keeps FHIR type hierarchy and known-type lists in local maps at [fhirTypeIsA](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:274) and [isKnownFHIRType](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:348), infers choice types from a hand-maintained suffix list at [infer_fhir_type](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1396), and infers complex types through field-name heuristics such as `name -> HumanName`, `address -> Address`, and `code -> CodeableConcept` at [fn_isType](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:6031). The Python fallback also has hand-maintained choice suffix/type maps at [_choice_type_suffix](/mnt/d/fhir4ds/fhir4ds/fhirpath/duckdb/udf.py:964).

This violates the repository rule that FHIR resource/type/choice behavior should come from schema metadata, generated model artifacts, or registries rather than generic runtime branches. It is especially risky after FP-15 because `is`/`as`/`ofType` parity now depends on these local maps staying synchronized between native C++, Python fallback, and generated metadata. Move these tables behind a generated metadata boundary or a shared registry, and add drift tests that compare native type resolution against the generated Python FHIR type metadata.

## Review Notes

Focused review probes were run against the current bundled native extension and a forced Python fallback connection. Full conformance was not rerun during this review-only pass; the FP-15 EXPLORER handoff reports the latest full baseline as 2822/2822 before this review.
