# Architect Handoff - SOF-VD-08 HISTORIAN

Structural audit result: clean. The SOF-VD-08 HISTORIAN fix keeps the retained legacy `viewdef.union.generate_union_all()` surface aligned with the main `SQLGenerator` rowset pipeline instead of maintaining a separate column-only SQL path. That improves abstraction integrity: parser/select dataclasses still feed one rowset-processing model, branch schema compatibility uses the existing effective schema model, and generated DuckDB SQL still evaluates FHIRPath through registered UDFs.

Issue summary:
- `QA-001` MEDIUM `RESOLVED`, category `SPEC_VIOLATION`
- New architectural findings: none
- QA retry: not needed

Golden standard checked:
- `select` rowsets cross-join; `unionAll` rowsets concatenate with duplicate preservation.
- Branch output compatibility is effective `(name, type, collection)` schema.
- Branch iterators, branch `where`, nested `select`, nested `unionAll`, and `repeat` must flow through the same rowset-generation path.
- Native/C++ DuckDB registration and forced Python fallback must agree on ViewDefinition execution boundaries.

Validation reviewed:
- Fresh SOF-VD-08 HISTORIAN probe passed across normal native/C++ registration and forced Python fallback.
- Focused union/ViewDefinition tests: `28 passed`
- ViewDefinition pytest: `852 passed`
- Full conformance: `2822/2822`
- Full package pytest: `7391 passed, 5 skipped, 9 warnings`

Recommended fix order: none. The only logged issue is resolved and verified.
