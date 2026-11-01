# QA Handoff: FP-06 EXPLORER

## Scope

- Chunk: FP-06
- Personality: EXPLORER
- Spec focus: FHIRPath §5.5.1 `iif`, §5.5.2 Boolean conversion, §5.5.3 Integer conversion
- Spec source: https://hl7.org/fhirpath/N1/

## Spec Grounding

- §5.5 conversion functions operate on singleton input; multiple input items signal an error and empty input propagates empty.
- §5.5.1 `iif` expects a Boolean criterion, returns the true branch only when the criterion is true, treats false or empty as otherwise, and must evaluate only the selected branch.
- §5.5.2 Boolean conversion accepts only the listed Boolean, Integer, Decimal, and case-insensitive String representations.
- §5.5.3 Integer conversion accepts Integer, Boolean, and String values matching `(\\+|-)?\d+` within Integer range.
- §6.8 gives dot invocation higher precedence than unary `+`/`-`; `-7.combine(3)` is the normative error pattern.

## Probe

Created `.temp/qa/fp06_explorer_probe.py` and ran it against:

- Native DuckDB/C++ extension: `.temp/qa/fp06_explorer_native.json`
- Forced Python fallback: `.temp/qa/fp06_explorer_fallback.json`

The probe covered 38 pathological/chained cases: lazy `iif` branches with invalid unselected expressions, optional otherwise branch, empty criterion, conversion chains inside `select`/`where`, conversion lexeme case/whitespace boundaries, overflow/underflow, data-dependent multi-item inputs, and unary precedence around conversion calls.

## Findings

### QA-001 MEDIUM

Forced Python fallback corrupts numeric string literals inside `iif(...)` before evaluation.

Reproducer:

```fhirpath
iif('1'.convertsToInteger(), 'T', 'F')
```

Native returns `['T']`; forced fallback returns `['F']`.

Initial root-cause hypothesis: `FHIRPathEvaluator.compile()` applies the no-whitespace quoted Quantity normalization regex inside ordinary string literals when another quoted argument appears later in the same function call, rewriting `'1'` to `'1 '`.

### QA-002 MEDIUM

Forced Python fallback leaks a sort-only descending marker into ordinary unary conversion expressions.

Reproducer:

```fhirpath
-1.convertsToInteger()
```

Native returns empty/NULL with `fhirpath_is_valid=false`; forced fallback returns `['DescendingSortMarker(True)']` with `fhirpath_is_valid=true`.

Initial root-cause hypothesis: `polarity_expression()` wraps non-numeric unary `-` results in `DescendingSortMarker` outside `sort()` context.

## Notes

Several data-dependent multi-item runtime errors correctly returned empty/NULL while `fhirpath_is_valid()` stayed true because the expression remains valid independent of the current row.
