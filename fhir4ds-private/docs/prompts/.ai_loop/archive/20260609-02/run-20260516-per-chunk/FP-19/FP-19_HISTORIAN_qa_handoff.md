# QA Handoff - FP-19 HISTORIAN

Scope covered FHIRPath §7 aggregate and §8 lexical elements using fresh probes only, avoiding `spec_comp/**`. I compared public DuckDB native C++ and forced Python fallback outputs across aggregate init/no-init, empty collection behavior, `$total`/`$this`/`$index` scoping, whitespace, line/block comments, delimited identifier escapes, keyword casing, malformed lexemes, and `fhirpath_is_valid` shape.

Findings:

- `QA-FP19-HISTORIAN-001` MEDIUM: Python fallback leaked aggregate loop scope. `(1|2).aggregate($this+$total,0) + $index` returned `[4]` in fallback/direct core but empty/NULL in native.
- `QA-FP19-HISTORIAN-002` MEDIUM: Forced fallback rejected valid leading comments such as `/* lead */ id` due wrapper regex prechecks.
- `QA-FP19-HISTORIAN-003` HIGH: Native `fhirpath_json()` reinterpreted string literals beginning with `[`/`{` as raw JSON, producing malformed or wrong JSON for `'['`, `'[1]'`, and `'{"a":1}'`.

All findings were reproducible with native-vs-forced-fallback probes and grounded in FHIRPath §7 aggregate scoping semantics and §8 lexical/comment/literal rules.
