# QA Handoff - FP-03 SKEPTIC

Scope: FHIRPath §5.1 Existence functions: `empty()`, `exists([criteria])`, `all(criteria)`, `allTrue()`, `anyTrue()`, `allFalse()`, `anyFalse()`, `subsetOf(other)`, `supersetOf(other)`, `count()`, `distinct()`, `isDistinct()`.

Spec basis: HL7 FHIRPath Normative Release v2.0.0 §5.1 and §4.3. §4.3 states expression parameters are evaluated per input item and may reference `$this` and `$index`. §5.1.2 defines `exists(criteria)` as `where(criteria).exists()`. §5.1.3 defines `all(criteria)` as true only when every item evaluates true, with empty input true. §5.1.4-§5.1.7 define boolean aggregate functions over Boolean collections with explicit empty-input results.

Hypotheses tested:
- Criteria functions might not preserve iteration context variables in native C++.
- Boolean aggregate functions might coerce non-Boolean values differently between native C++ and Python fallback.
- Empty/null navigation and `count()` might diverge between backends.
- Root-context arguments for `subsetOf()`/`supersetOf()` might evaluate against the wrong scope.
- `distinct()`/`isDistinct()` might diverge on repeated FHIR Quantity-shaped objects.

Findings:
- QA-001 HIGH: Native C++ DuckDB does not expose `$index` inside `exists(criteria)` or `all(criteria)`. Reproducer on `{"resourceType":"Patient","a":[10,20,30]}`: native returns `false` for `a.exists($index = 1)` and `a.all($index < 3)`, while Python fallback returns `true` for both. `where($index = 1)` and `select($index)` already work natively, so this is isolated to these §5.1 criteria functions.
- QA-002 MEDIUM: Native C++ boolean aggregates return concrete `false` for non-Boolean input collections, while Python fallback raises/catches `FHIRPathError` and public wrappers return empty/NULL. Reproducer on `{"strings":["true","false","x"]}`: native returns `[false]` for `strings.allTrue()`, `strings.anyTrue()`, and `strings.allFalse()`; fallback returns empty/NULL.

Non-findings:
- `empty()`, `exists()`, `count()`, null navigation, FHIR object `distinct()`, `isDistinct()`, `subsetOf()`, and `supersetOf()` matched between native and Python fallback for normal FHIR-shaped JSON probes.
- `subsetOf()`/`supersetOf()` root-resource argument evaluation matched for `contained.meta.tag.subsetOf(meta.tag)` and `meta.tag.supersetOf(contained.meta.tag)`.

Recommended remediation:
- In `extensions/fhirpath/src/fhirpath/evaluator.cpp`, set and restore `index_context_` per item in both `evalExists()` and `fn_all()`.
- Make `fn_allTrue()`, `fn_anyTrue()`, `fn_allFalse()`, and `fn_anyFalse()` raise `FHIRPathSpecError` when an item is not Boolean/JSON Boolean so public native UDFs return empty/NULL consistently with fallback resilience.
- Add parity tests covering native and forced Python fallback for these cases.
