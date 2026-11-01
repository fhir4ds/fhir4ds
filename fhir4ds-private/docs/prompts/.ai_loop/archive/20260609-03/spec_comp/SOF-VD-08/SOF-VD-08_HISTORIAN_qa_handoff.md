# QA Handoff: SOF-VD-08 HISTORIAN

Scope: SQL-on-FHIR ViewDefinition `select.unionAll`, HISTORIAN pass, iteration 1.

Spec anchors consulted:
- SQL-on-FHIR v2.0.0 ViewDefinition `Unions`: `unionAll` concatenates nested select rowsets, branch schemas must match by column count/name/order/FHIR type, and duplicate rows are preserved like SQL `UNION ALL`.
- SQL-on-FHIR v2.0.0 `Composing Multiple Selects and Unions`: `unionAll` rowsets compose like ordinary `select` rowsets and can be nested.

Fresh probes executed:
- `.temp/qa/sof_vd08_historian_probe.py`
- Official `union.json` fixtures, including basic unions, duplicate preservation, empty branches, `forEachOrNull`, nested unions, one empty operand, column mismatch, and order mismatch.
- Additional branch scope cases covering root/select/branch `where`, duplicate branch preservation, branch `forEach`, branch `forEachOrNull`, branch `repeat`, nested `select`, nested `unionAll`, missing/name/order/type/collection schema errors, native-loaded DuckDB, forced Python fallback, and the SKEPTIC empty-`unionAll` parser guard.

Result: no product defects found. The current implementation matches the spec surface probed for SOF-VD-08.

Validation:
- Fresh probe: PASS
- Focused union/spec pytest: 95 passed
- ViewDefinition pytest: 953 passed
- ViewDefinition conformance: 134/134
- Full conformance: 2822/2822
