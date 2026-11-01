# Code Review Findings

Scope: SPEC COMPLIANCE MILESTONE REVIEW after 25 completed chunks. Reviewed the current tree through CQL-05, with emphasis on CQL primitive, clinical, temporal, logical, and structural type changes from CQL-01 through CQL-05, plus the still-open review-20 FHIRPath risks. This was review-only; no fixes were implemented and `spec_schedule.json` was not modified.

## Findings

### REV-001 - HIGH - Native FHIRPath Section 5.1 arity validation remains incomplete

Evidence: [evalFunction](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1649) still has exact arity guards for many helpers, but omits Section 5.1 helpers such as `exists`, `all`, `subsetOf`, `supersetOf`, `count`, `empty`, `distinct`, `isDistinct`, `hasValue`, and Boolean aggregates. Dispatch then accepts extra or missing arguments at [evalExists](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1548), [count/empty/hasValue](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1738), [all](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:2636), and [subsetOf/supersetOf](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:2897).

Fresh spot check: `fhirpath_is_valid('arr.count(true)')` returns `true` on native and `false` on forced Python fallback.

Proposed fix: add exact signature checks before native semantic dispatch and keep native sqllogictest plus forced fallback parity coverage together.

### REV-002 - MEDIUM - Native `fhirpath_timestamp` still accepts invalid resource-backed DateTime strings

Evidence: [IsTimestampValue](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1614) accepts strings through [IsDateTimeText](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1532), which checks shape but not calendar/time/timezone ranges before [FhirpathTimestampFunction](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1676) returns the value.

Fresh spot check: `fhirpath_timestamp(..., 'dt_bad')` over `"2024-13-01T00:00:00"` returns that invalid string on native and `NULL` on forced Python fallback.

Proposed fix: route wrapper validation through the strict temporal parser used by literal/conversion paths, or make `IsDateTimeText()` enforce identical range rules.

### REV-003 - MEDIUM - `fhirpath_quantity` typed wrappers accept malformed Quantity objects

Evidence: native [IsQuantityValue](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath_extension.cpp:1628) only checks for a `value` key and `code` or `unit`; fallback [fhirpath_quantity_udf](/mnt/d/fhir4ds/fhir4ds/fhirpath/duckdb/udf.py:2354) has the same shape-only check.

Fresh spot check: `{"value":"5","unit":"mg"}` is returned by both native and forced fallback wrappers instead of row-resilient `NULL`.

Proposed fix: require finite JSON-numeric `value` plus string `code` or `unit` for typed Quantity wrappers.

### REV-004 - MEDIUM - Native Unicode `upper()` / `lower()` still use an incomplete hand-maintained table

Evidence: [fn_upper](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:3406) and [fn_lower](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:3495) maintain local code-point mappings. Review-20 examples such as `ǆ`, `ſ`, `ẞ`, and ligature expansion remain outside a generated Unicode data path.

Proposed fix: replace the local table with generated Unicode case data or a Unicode-aware library path; test one-to-one and one-to-many mappings against the Python fallback.

### REV-005 - MEDIUM - FHIR model/type knowledge remains embedded in generic FHIRPath runtime code

Evidence: native [fhirFieldType](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1171) still hardcodes primitive field metadata, including the FP-20 `subjectType` addition. Python fallback has parallel generated/lookup paths such as [_get_choice_type_lookup](/mnt/d/fhir4ds/fhir4ds/fhirpath/duckdb/udf.py:1134). This remains a drift risk and violates the model-knowledge boundary until native and fallback type metadata share a generated registry.

Proposed fix: move native type hierarchy, field primitive metadata, and choice suffix behavior behind generated/shared model metadata with drift tests.

### REV-006 - MEDIUM - FHIRPath string/STU helper arity validation remains incomplete

Evidence: fallback [_FHIRPATH_STRING_SEARCH_ARITY](/mnt/d/fhir4ds/fhir4ds/fhirpath/duckdb/udf.py:389) and native [evalFunction](/mnt/d/fhir4ds/extensions/fhirpath/src/fhirpath/evaluator.cpp:1649) still do not define exact signatures for every string/STU helper called out in review-20, including `trim`, `split`, `join`, `matchesFull`, `escape`, `unescape`, `encode`, and `decode`.

Fresh spot check: `fhirpath_is_valid('s.trim(1)')` returns `true` on both native and forced fallback.

Proposed fix: add exact signatures to both validation layers; result UDFs can remain row-resilient while `fhirpath_is_valid()` rejects malformed call shapes.

### REV-007 - HIGH - Qualified ValueSet references from included CQL libraries lower to missing CTEs

Evidence: after CQL-02 added `valueset ... codesystems { ... }` preservation, included library valuesets are copied into the parent context without alias-qualified keys at [include_handler.py](/mnt/d/fhir4ds/fhir4ds/cql/translator/include_handler.py:355). `_translate_qualified_identifier()` treats any `Lib.Name` whose first segment is an include as an included definition; if no definition was registered, it silently generates a subquery against the expected CTE name at [fhir4ds/cql/translator/expressions/_core.py](/mnt/d/fhir4ds/fhir4ds/cql/translator/expressions/_core.py:1122).

Fresh probe:

```text
include Inc called Inc
define Ref: Inc.Diabetes
define IsVS: Inc.Diabetes is ValueSet
```

where `Inc` declares `valueset Diabetes: 'http://example.org/vs' codesystems { LOINC }`, translates to:

```text
Ref  -> (SELECT * FROM "Inc.Diabetes")
IsVS -> json_extract_string((SELECT * FROM "Inc.Diabetes"), '$.resourceType') = 'ValueSet'
```

Executing either expression fails with `Catalog Error: Table with name Inc.Diabetes does not exist`.

Proposed fix: register included ValueSet/CodeSystem/Code/Concept symbols under both their local and alias-qualified names or resolve `Lib.ValueSetName` through `context.includes[Lib]` before falling back to CTE generation. Unknown included symbols should raise a clear translation error rather than synthesize missing CTE SQL.

### REV-008 - HIGH - Generic CQL ValueSet membership embeds QICore-specific behavior

Evidence: Python [valueset.py](/mnt/d/fhir4ds/fhir4ds/cql/duckdb/udf/valueset.py:440) and native [valueset.cpp](/mnt/d/fhir4ds/extensions/cql/src/cql/valueset.cpp:16) hardcode the QICore `qicore-notDoneValueSet` extension in generic `in_valueset` behavior. If a resource has no coding but has that extension, [createValuesetMembershipUdf](/mnt/d/fhir4ds/fhir4ds/cql/duckdb/udf/valueset.py:558) returns `true`; native mirrors that at [extract_codes_with_not_done_valueset](/mnt/d/fhir4ds/extensions/cql/src/cql/valueset.cpp:557).

Fresh spot check: a `MedicationRequest.medicationCodeableConcept` with only a `qicore-notDoneValueSet` extension and no `coding` matched a loaded target ValueSet.

Proposed fix: move QICore negation-profile semantics into a profile/IG adapter or registry-driven configuration path. Generic terminology membership should not contain IG-specific URLs that change output.

### REV-009 - MEDIUM - Conversion macro private-function registration swallows all exceptions

Evidence: [_create_private_function](/mnt/d/fhir4ds/fhir4ds/cql/duckdb/macros/conversion.py:13) catches `Exception` and silently `pass`es. It is used for spec-aware `ToDate`, `ToDateTime`, and `ToTime` private helpers before public macros are created at [conversion.py](/mnt/d/fhir4ds/fhir4ds/cql/duckdb/macros/conversion.py:78). An unexpected registration failure can leave public macros pointing at missing private functions or mask a registration divergence between native-loaded and forced fallback connections.

Proposed fix: catch only expected duplicate-registration/catalog exceptions and log them. Unexpected failures should raise during registration so public conversion surfaces fail early and visibly.

## Review Notes

Review-only probes were run for representative native-vs-fallback FHIRPath risks, included-library ValueSet lowering, and generic CQL ValueSet membership behavior. Full conformance was not rerun in this review pass; CQL-05 EXPLORER reported the latest full baseline as `2822/2822`.
