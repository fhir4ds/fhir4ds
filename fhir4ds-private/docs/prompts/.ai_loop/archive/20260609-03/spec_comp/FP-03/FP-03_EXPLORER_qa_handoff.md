# QA Handoff - FP-03 EXPLORER

Spec grounding:
- FHIRPath Normative Release section 5.1.2 defines `exists(criteria)` as shorthand for `where(criteria).exists()`.
- Section 5.2.1 requires `where(criteria)` conditions to evaluate to a single Boolean; any other result signals an error.
- Section 5 function rules allow expression parameters to use `$this` and `$index`; logical operators remain operators, not function names.

Probe:
- Created `.temp/qa/fp03_explorer_rerun_probe.py`.
- Compared native C++ DuckDB registration and forced Python fallback registration in isolated subprocesses.
- Covered chained `empty()`/`exists()`, criteria lambdas, `$index`, empty criteria, Boolean aggregate defaults, invalid Boolean aggregate inputs, `subsetOf`/`supersetOf` empty defaults, and `distinct()`/`isDistinct()` equality boundaries for numerics, strings, temporals, objects, and quantities.

Findings:
- `QA-001` MEDIUM: native `exists(criteria)` short-circuits after the first true criterion and skips a later invalid multi-item Boolean criterion. This diverges from the spec shorthand `where(criteria).exists()` and from forced Python fallback row resilience.
- `QA-002` MEDIUM: forced Python fallback `fhirpath_is_valid()` mistakes logical operators followed by `(` for unknown function calls, e.g. `a.all(($this > 0) and ($index < 3))`, returning false while native returns true and both evaluate successfully.

Recommended fix:
- Make native `evalExists` validate every criterion result while remembering whether any item matched.
- Teach the fallback unknown-function scanner to ignore FHIRPath operator keywords before `(`.
