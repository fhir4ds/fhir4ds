# QA Handoff — SOF-VD-07 SKEPTIC

Scope audited: SQL-on-FHIR ViewDefinition `select.repeat` parser validation, SQL generation, DuckDB execution, official repeat fixtures, native C++ registration, and forced Python fallback registration. Fresh probes were built from the current code only.

Findings:
- QA-001 HIGH: repeat entries were treated as simple dotted JSON keys, so full FHIRPath expressions such as `item.where(text.exists())` returned no rows in both native and fallback paths.
- QA-002 HIGH: deep repeat traversal diverged; a 205-level item chain returned 200 rows on native and 0 rows on forced fallback.
- QA-003 MEDIUM: duplicate repeat paths multiplied the same repeated nodes instead of unioning duplicate hits.
- QA-004 MEDIUM: parser accepted scalar JSON `repeat: "name"` and normalized it to an array.

Spec basis: SQL-on-FHIR ViewDefinition.select.repeat is a 0..* string array of FHIRPath expressions; a runner evaluates each expression from the current context node, recursively applies the same paths, continues until no more matches are found at any depth, and unions results from all levels and paths.
