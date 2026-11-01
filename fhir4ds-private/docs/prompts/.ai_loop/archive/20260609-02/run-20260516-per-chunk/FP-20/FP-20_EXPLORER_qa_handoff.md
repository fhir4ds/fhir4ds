# QA Handoff - FP-20 EXPLORER - 2026-05-17

Scope: FHIRPath §9 environment variables, §10 type/reflection, §11 type safety, and §12 grammar/model-info/URI/media-type shapes. I avoided `spec_comp/**` content and used current source, current rules, official FHIRPath spec sections, and fresh probes only.

Probes covered native C++ and forced Python fallback DuckDB UDFs independently across `%context`, `%resource`, `%rootResource`, quoted and delimited variables, malformed variable syntax, nested `select()`/`where()`/`aggregate()` variable contexts, `type()`/`is()`/`as()` over primitives/resources/BackboneElement/Reference/Attachment/URI/media-type fields, invalid namespace/specifier shapes, and public wrapper resilience.

Finding: `QA-FP20-EXP-001` HIGH backend parity. Native DuckDB supports `defineVariable()` publicly, but forced Python fallback raised `NotImplementedError` for result UDFs and reported invalid redefinition/system-overwrite cases as valid. Repro examples:

- Native `defineVariable('x', id).select(%x)` returned `['p1']`; forced fallback `fhirpath()` raised `NotImplementedError: defineVariable`.
- Native `defineVariable('x', id).defineVariable('x', name.family).select(%x)` returned empty/NULL with `fhirpath_is_valid=false`; fallback raised on result UDFs and returned `fhirpath_is_valid=true`.
- Native `a.where(defineVariable('leak', $this).exists()).select(%leak)` returned empty/NULL, demonstrating callback-local variable restoration that fallback did not implement.

Spec grounding: FHIRPath §9 defines environment-variable access; §12.1 says the grammar is the source of truth for valid expression forms; §12.2 defines model-info/reflection expectations. The bug is primarily public native/fallback parity for a native-exposed environment-variable helper and invalidity reporting on the DuckDB surface.
