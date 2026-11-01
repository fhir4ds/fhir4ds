# QA Handoff: SOF-VD-06/SKEPTIC

Scope: SQL-on-FHIR ViewDefinition `select.forEach` and `select.forEachOrNull`.

Spec anchor:
- SQL-on-FHIR v2.0.0 defines `ViewDefinition.select.forEach` as `0..1 string`, selecting parent elements and producing one row per selected element.
- `forEachOrNull` is the same iterator shape, but preserves a single null-valued nested row when the selected collection is empty.
- The functional model treats `forEach` as flattening, `select` as cross-joining row sets, and child selects as relative to the active iterator context.

Hypotheses tested:
- Present JSON `null` for iterator fields may be confused with absence because parser code used `select_data.get(...)`.
- Non-string and empty-string iterator expressions should fail before SQL generation.
- `forEach` should drop resources with empty collections; `forEachOrNull` should preserve one row with null nested values.
- Parent columns, nested select columns, `%context`, `%resource`, `%rootResource`, and `%rowIndex` should remain correct in iterated contexts on native/default and forced Python fallback registrations.

Finding:
- `SOFVD06-SKEPTIC-001` HIGH: `parse_view_definition()` accepts present JSON `null` for `select.forEach` and `select.forEachOrNull`, treats it as absent, and allows SQL generation. This violates the `0..1 string` logical-model field shape and FHIR JSON primitive-null boundary.

Fresh evidence:
- `.temp/qa/sof_vd06_skeptic_probe.py` currently fails before remediation with `AssertionError: present-null forEach was accepted but should be rejected`.

