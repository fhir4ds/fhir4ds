# Architect Handoff — SOF-VD-07 HISTORIAN

Structural audit result: clean. The fix preserves the intended boundary: ViewDefinition SQL still lowers repeat through `fhirpath_repeat`, while current-focus semantics are owned by the DuckDB FHIRPath evaluator surfaces. No generator-specific special case was added for `$this`, so direct UDF calls, repeat expressions, and generated ViewDefinition columns share the same behavior.

Issues by category:
- `SPEC_VIOLATION`: 1 found, 1 verified.

QA audit:
- QA was sufficient for HISTORIAN scope. It covered parser validation, generated SQL, direct native/fallback parity, recursive traversal, multi-path union behavior, deep nesting, and repeated-node column context. No `RETRY_QA` needed.

Recommended fix order:
- None. `QA-001` is verified and no additional architecture findings were logged.

Validation reviewed:
- Fresh repeat probe passed.
- ViewDefinition/FHIRPath variable pytest passed 898/898.
- Full conformance passed 2822/2822.
- Full package pytest passed 7386 with 5 skips and 9 warnings.
