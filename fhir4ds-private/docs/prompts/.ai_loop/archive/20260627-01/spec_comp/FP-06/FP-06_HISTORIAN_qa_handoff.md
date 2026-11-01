# QA Handoff - FP-06 HISTORIAN

Date: 2026-06-12

Scope: FHIRPath §5.5.1 `iif`, §5.5.2 Boolean Conversion, and §5.5.3 Integer Conversion across native DuckDB/C++ and forced Python DuckDB fallback.

Spec source: official HL7 FHIRPath continuous-build source, `input/pages/index.md` lines 205-222.

Normative summary:
- §5.5 conversion functions operate on empty-or-singleton input collections; multi-item inputs signal an error to the calling environment.
- `iif(criterion, true-result, otherwise-result)` evaluates the criterion once, evaluates only the selected branch, treats empty criterion as false, and applies singleton Boolean evaluation to non-empty singleton criteria.
- `iif` does not set its own `$index`; an outer scoped `$index` remains visible.
- `toBoolean()` accepts only the listed Boolean, Integer, Decimal, and case-insensitive String representations; unrecognized values return empty, and `convertsToBoolean()` returns false.
- `toInteger()` accepts Integer, Long, exact integer strings matching `(\+|-)?\d+`, and Boolean values; unrecognized or out-of-range values return empty, and `convertsToInteger()` returns false.

Hypotheses tested:
- `iif()` branch arguments are lazily evaluated in result UDFs, including unknown or erroring functions in the unselected branch.
- Singleton non-Boolean `iif` criteria, including numeric zero, select the true branch.
- Multi-item conversion inputs and `iif` criteria produce public empty/NULL results rather than leaking exceptions.
- Boolean conversion aliases are exact and case-insensitive, with no whitespace trimming.
- Integer conversion enforces the exact integer-string grammar and 32-bit Integer literal range consistently in native and forced fallback paths.

Fresh evidence:
- Discovery matrix compared `fhirpath`, `fhirpath_json`, `fhirpath_text`, `fhirpath_number`, `fhirpath_bool`, and `fhirpath_is_valid` for 37 expressions on native and forced fallback DuckDB connections.
- New focused probe: `.temp/qa/fp06_historian_fresh_probe.py`.
- Pre-fix probe result: failed only on `2147483648.toInteger()` in forced fallback. Native returned `([], None, None, None, None, False)`. Forced fallback raised `FHIRPathSyntaxError` through the public result query.

Issue opened:
- `QA-001` MEDIUM `OPEN`: forced Python fallback result UDFs propagate out-of-range Integer literal syntax errors for `2147483648.toInteger()` instead of returning native-matching row-resilient empty/NULL results with `fhirpath_is_valid=false`.

Retry QA after architect veto:
- Expanded `.temp/qa/fp06_historian_fresh_probe.py` to include `-2147483649.toInteger()`, `-2147483649.convertsToInteger()`, and a fresh invalid surrogate string literal control for the same native invalid-expression result-wrapper class.
- Pre-fix retry result: native DuckDB failed immediately with `Invalid FHIRPath expression: -2147483649.toInteger()`, while the forced fallback path had already been made row-resilient by the `QA-001` fix.
- Confirmed `ARCH-001` HIGH `CONFIRMED`.

Review finding intersection:
- `REV-FP-001` is the same public-wrapper resilience pattern but for invalid surrogate string literals; it is not directly fixed by this FP-06 issue.
- `REV-FP-002` through `REV-FP-004` do not intersect this chunk.
