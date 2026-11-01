# QA Handoff: SOF-VD-06/HISTORIAN

Personality: HISTORIAN
Iteration: 1
Result: PASSED, no product defects found.

Spec anchors:
- SQL-on-FHIR v2.0.0 ViewDefinition definitions: `select.select` is nested relative to the parent expression; `select.forEach` is `0..1 string` and produces one row for each selected element; `select.forEachOrNull` is `0..1 string` and preserves a null-valued row for empty collections.
- SQL-on-FHIR latest functional model: `forEach`/`forEachOrNull` flatten nested collections; `forEach` removes records with no results while `forEachOrNull` keeps an empty record; both set `%rowIndex` to the 0-based index of the current element.

Fresh QA coverage:
- Wrote `.temp/qa/sof_vd06_historian_probe.py`.
- Verified `forEach` row multiplication, nested current focus, and empty-collection suppression.
- Verified `forEachOrNull` preserves one row with null nested values while `%resource` and `%rootResource` still resolve against the root resource.
- Verified `%context`, `%resource`, `%rootResource`, and `%rowIndex` in nested iterator columns.
- Verified `%rowIndex` embedded in `where`, column expressions, and child iterator expressions.
- Rechecked SKEPTIC boundary: present JSON null for `forEach` and `forEachOrNull` raises `ParseError`; direct dataclass mutual exclusion raises `ValidationError`.
- Ran native-loaded DuckDB registration and forced Python fallback for the fresh execution probe.

Validation:
- Fresh SOF-VD-06 HISTORIAN probe: PASS.
- Official `foreach`/`row_index` execution pytest: 31 passed.
- Focused native/fallback iterator integration pytest: 11 passed.
- Parser/UNNEST focused pytest: 40 passed.
- Full ViewDefinition pytest: 950 passed.
- ViewDefinition conformance: 134/134.
- Full conformance: 2822/2822.

Issues logged: none.
