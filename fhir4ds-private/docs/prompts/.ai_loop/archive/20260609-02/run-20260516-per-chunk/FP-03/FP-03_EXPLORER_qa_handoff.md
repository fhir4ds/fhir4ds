## QA Handoff: FP-03 EXPLORER

Scope: FHIRPath N1 section 5.1 existence functions, with public DuckDB native extension and Python fallback comparison.

Spec anchor: https://hl7.org/fhirpath/N1/ section 5.1. The relevant rules are that `exists(criteria)` is shorthand for `where(criteria).exists()`, `all(criteria)` requires the criteria to evaluate true for each item, `where(criteria)` errors unless the criteria result is a single Boolean, and Boolean aggregate functions take Boolean collections.

Exploration performed:
- Compared native DuckDB UDF outputs with direct Python fallback UDF helpers for `empty`, `exists(criteria)`, `all(criteria)`, Boolean aggregates, membership/distinct, and empty-collection defaults.
- Stressed criteria functions with non-Boolean singleton and multi-item criteria such as `nums.all($this)` and `name.all(given)`.
- Stressed Boolean aggregates with mixed-type literal collections where short-circuiting could hide later invalid items.

Findings:
- `QA-FP03-EXPLORER-001`: native C++ `all(criteria)` applies truthiness to non-Boolean criteria and returns `true` for cases where the fallback returns empty/NULL. Example: `nums.all($this)` on `[1,2]`.
- `QA-FP03-EXPLORER-002`: both native C++ and Python fallback Boolean aggregates can short-circuit before validating all items. Examples: `true.combine('x').anyTrue()` and `false.combine('x').anyFalse()` return `true` despite the non-Boolean item.

Recommended remediation:
- Add a shared strict criteria Boolean helper in the native evaluator and use it for `where`, `exists(criteria)`, and `all(criteria)`.
- Validate the entire input collection in all four Boolean aggregate functions before applying the aggregate truth table.
- Mirror aggregate validation in Python core existence functions and add parity regression tests for native and forced fallback public UDFs.
