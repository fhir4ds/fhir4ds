# QA Handoff - FP-12 SKEPTIC

Scope: FHIRPath §5.8 tree navigation and §5.9 utility functions: `children()`, `descendants()`, `trace(name, [projection])`, `now()`, `timeOfDay()`, `today()`.

Spec checked: official FHIRPath normative release §5.8 says `children()` returns all immediate child nodes and `descendants()` is shorthand for `repeat(children())`; §5.9.1 says `trace()` returns input unchanged but logs the projection result when supplied; §5.9.2 says current date/time functions are deterministic within one expression and timestamp source is implementation-defined.

Hypotheses tested:
- Native `children()` may skip JSON null children due explicit `yyjson_is_null()` checks.
- `descendants()` may inherit the same null-loss because it delegates to `children()`.
- Python core `trace(name, projection)` may ignore projection because `doInvoke()` special-cases trace parameters.
- Current date/time functions may be nondeterministic across repeated calls in one expression.
- Native and fallback date/time utilities may differ in timezone policy.

Findings:
- `QA-001` HIGH: native C++ DuckDB `children()` and `descendants()` drop null children. Forced Python fallback preserves them. Reproducer used a Patient with `active:null` and `name[0].family:null`.
- `QA-002` MEDIUM: Python core `trace(name, projection)` logs input instead of projection through `traceFn`. Return value remains correct.

Checks run:
- Native vs forced Python fallback DuckDB probes for `children()`, `descendants()`, `trace()`, `now()`, `today()`, and `timeOfDay()`.
- Direct Python core `evaluate(..., options={'traceFn': cb})` probe for trace projection.

Non-issues:
- Native current date/time uses UTC while fallback uses local time; §5.9.2 leaves timestamp source to implementation policy. Deterministic equality checks passed for `now() = now()`, `today() = today()`, and `timeOfDay() = timeOfDay()` in both backends.
