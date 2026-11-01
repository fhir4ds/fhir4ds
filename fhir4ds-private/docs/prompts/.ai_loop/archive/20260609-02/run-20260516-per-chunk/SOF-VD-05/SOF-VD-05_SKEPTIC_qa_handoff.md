# QA Handoff — SOF-VD-05 SKEPTIC

Phase: QA
Personality: SKEPTIC
Scope: SQL-on-FHIR ViewDefinition nested select/contentReference.

Spec grounding:
- SQL-on-FHIR v2.1.0-pre ViewDefinition declares `select.select` as a recursive nested select and says `forEach` defaults effectively to `$this`.
- The same spec says `forEachOrNull` produces a row with null values when the selected collection is empty.
- Multiple select semantics say parent/child selects repeat parent values for each child item, while sibling selects are cross joined.

Hypotheses probed:
- Deep recursive nested selects might stop parsing or generating after one level.
- Child selects without their own row generator might fail to inherit the parent focus/default `$this`.
- Parent/root columns might not repeat through child row generators.
- Sibling select rowsets might concatenate instead of cross joining.
- Duplicate parent/child column names might be accepted until SQL execution.
- An enclosing `forEachOrNull` null row might be dropped by a nested child `forEach`.

Finding:
- QA-001 HIGH OPEN: `forEachOrNull` followed by a nested child `forEach` drops resources whose outer collection is empty. Reproducer used a Patient with no `contact` and a view selecting root `id` plus `forEachOrNull: contact` containing child `forEach: telecom`. Actual result omitted the patient entirely; expected result includes the root id with null child columns.

Validation/probes:
- Parser recursion, default `$this` nested select, parent/child row combination, sibling cross join, duplicate validation, and empty nested select with parent columns were directly probed in `.temp/qa`-style scratch execution from stdin.
- Normal registration and forced Python fallback produced the same failure for QA-001. The normal registration returned `False` for native extension load in this environment, so no distinct C++ execution path was available for this ViewDefinition probe.

Next phase:
- Implement a focused SQL generation fix so nested `forEach` preserves one null child row only when an enclosing `forEachOrNull` context variable is NULL, while keeping ordinary child `forEach` inner-join semantics for real parent elements.
