# QA Handoff - SOF-VD-11/SKEPTIC

Personality: SKEPTIC

Chunk focus: SQL-on-FHIR ViewDefinition runner/examples: tabular execution,
Patient/Observation examples, array unrolling, filters, type coercion,
official spec_tests parity, and native C++ versus forced Python fallback.

Hypotheses attacked:
- Shared `resources` table execution might disagree with per-resource-table
  execution or miss root resource filtering.
- Patient array unrolling via `forEach` could preserve wrong parent rows or
  produce unstable row shape.
- Observation filters plus decimal type coercion could diverge between native
  C++ and forced Python fallback.
- View Runner helper functions `getResourceKey()` and `getReferenceKey()`
  could still be fallback-only.
- Local official `spec_tests` row equality could pass through the conformance
  runner but fail under native C++ when the bundled extension is actually
  loaded.

Fresh evidence:
- Added scratch probe:
  `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd11_skeptic_probe.py`.
- Custom runner cases passed under native C++ and forced fallback before the
  broad fixture sweep:
  `patient_simple_typed`, `patient_address_foreach`, and
  `observation_filter_decimal_and_reference`.
- The broad native C++ official fixture sweep failed on
  `fhir4ds/viewdef/tests/spec_tests/fn_boundary.json`.

Finding:
- `SOF-VD-11-SKEPTIC-001` HIGH is open.
- Official fixture `fn_boundary.json` expects decimal `lowBoundary()` /
  `highBoundary()` over `value.ofType(Quantity).value` where
  `valueQuantity.value` is authored as JSON `1.0` to return `0.95` and `1.05`.
- Native C++ returned `-0.5` and `0.5`; direct probe showed
  `value.ofType(Quantity).value.precision()` returned `0`.
- Forced Python fallback returned precision `1` and the expected boundaries.

Likely root cause:
- Native member access wraps JSON numeric values without preserving the raw
  JSON number text in `FPValue.source_text`. Boundary functions therefore see
  `1.0` as precision `0` after generic double formatting.

Spec anchor:
- FHIRPath `lowBoundary` / `highBoundary` define least/greatest possible value
  at the input precision; local SQL-on-FHIR v2 official fixture
  `fn_boundary.json` encodes the expected View Runner result.

Post-remediation note:
- The expanded native official sweep also exposed related parity gaps in
  typed FHIR `date`/`dateTime`/`time` boundary execution and root-level
  `where(criteria)` filtering. These were kept under the same SOF-VD-11 runner
  parity issue because they were found by the same fresh official
  `spec_tests` runner probe and affect the same parser/generator/DuckDB
  agreement surface.
