# QA Handoff - SOF-VD-09 SKEPTIC

Scope probed: SQL-on-FHIR ViewDefinition root `where` parsing, generated SQL, DuckDB execution, native C++ registration versus forced Python fallback, constants, root-resource scope under `forEach`, true/false/empty/null filtering, non-Boolean results, and `where.description` retention.

Spec basis checked directly against SQL-on-FHIR v2.0.0:
- `ViewDefinition.where` is 0..* FHIRPath constraints and every constraint must evaluate true for inclusion.
- `ViewDefinition.where.path` input context is the resource collection for the declared `resource`; constants can be referenced as `%name`.
- `ViewDefinition.where.description` is optional human-readable string metadata.
- The functional model `where` keeps only rows where `fhirpath(expr, row) == true`.

Hypotheses tested:
- Numeric FHIRPath results might be coerced into SQL truthiness at `fhirpath_bool`.
- Empty, false, and null root predicates might leak rows.
- Root `where` might accidentally bind to an iterator alias instead of the root resource.
- Constant substitution inside complex root predicates might drift between native and fallback.
- `where.description` might be dropped or shape-unvalidated.

Findings:
- QA-001 HIGH: root `where` accepts integer `1`/`0` as Boolean via `fhirpath_bool`; both native and forced fallback include rows for non-Boolean numeric predicates such as `valueInteger` and literal `1`.
- QA-002 MEDIUM: root `where.description` accepts non-string present values (`5`, `None`) instead of enforcing the logical-model string/markdown boundary.

Clean behavior observed:
- `active` root Boolean filtering includes only true and excludes false/missing rows.
- Complex root predicate `gender = %WantedGender and name.family.exists()` retains root scope when the select uses `forEach: telecom`; generated SQL applies `fhirpath_bool(t.resource, ...)`.
- Valid string `where.description` is retained through parsing.

Artifacts:
- `.temp/qa/sof_vd_09_probe.log`
- `.temp/qa/sof_vd_09_description_probe.log`
