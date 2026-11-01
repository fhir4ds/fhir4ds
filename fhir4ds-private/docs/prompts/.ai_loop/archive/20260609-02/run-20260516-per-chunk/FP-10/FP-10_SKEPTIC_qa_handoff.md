## QA Handoff - FP-10 SKEPTIC

Scope: FHIRPath N1 §5.6.6-§5.6.12 string transform functions: `upper()`, `lower()`, `replace()`, `matches()`, `replaceMatches()`, `length()`, `toChars()`.

Normative anchor: §5.6 functions operate on singleton String inputs; non-String or multi-item inputs signal an error to the calling environment. Empty input and empty transform arguments propagate empty where specified. `replace('', sub)` surrounds each character. `replaceMatches('', sub)` is covered by the official local R4 fixture as unchanged input. `matches()` is case-sensitive, single-line/DOTALL, and repo conformance treats it as full-string matching.

Hypotheses tested:
- Native C++ transform functions may coerce invalid values through `toString()`.
- Regex transform paths may differ between native and forced Python fallback.
- Unicode length/chars and empty pattern handling may count bytes instead of code points.
- Direct helper APIs may lag behind core/public UDF semantics.

Probe artifact: `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/fp10_probe.py`.

Findings:
- `QA-001` HIGH: native C++ public UDFs coerce invalid String-function inputs/arguments for `matches()`, `replace()`, `replaceMatches()`, and `toChars()` instead of returning empty/NULL like the forced Python fallback.
- `QA-002` MEDIUM: direct helper module `fhir4ds.fhirpath.duckdb.functions.string` uses partial non-DOTALL `matches()`, treats empty `replaceMatches()` regex as insert-between-chars, and lacks `toChars`.

Non-findings:
- Native and fallback agree for valid `upper()`, `lower()`, `replace()`, `matches()`, `replaceMatches()`, `length()`, and `toChars()` basics, including precomposed and decomposed Unicode code-point behavior.
