# QA Handoff: FP-12 SKEPTIC

## Scope

FHIRPath Normative Release sections 5.8 Tree Navigation and 5.9 Utility Functions:
`children()`, `descendants()`, `trace(name, [projection])`, `now()`,
`timeOfDay()`, and `today()`.

Spec source verified directly: https://hl7.org/fhirpath/N1/ sections 5.8.1,
5.8.2, 5.9.1, and 5.9.2.

## SKEPTIC Hypotheses

1. Native C++ dispatcher would ignore extra arguments for tree/clock functions.
2. Native `trace()` would be implemented as identity and ignore required args.
3. Fallback validation might accept zero-argument `trace()` due permissive registry metadata.
4. `children()` might drop JSON null children while normal navigation skips null.
5. `descendants()` might include the input node itself or miss nested content.
6. Clock functions might drift within a single expression.
7. `trace(name, projection)` might return projection instead of input.

## Probe

Fresh probe: `.temp/qa/fp12_skeptic_probe.py`

Coverage included native C++ DuckDB registration and forced Python fallback for:

- JSON null child preservation in `children()` and `descendants()`
- nested descendant traversal
- non-resource primitive inputs
- invalid arity for tree and clock functions
- `trace` missing/wrong/extra arguments
- trace identity with projection
- clock type/shape/stability within one expression

## Findings

`QA-001` MEDIUM: native accepted argument-bearing `children(1)`,
`descendants(1)`, `now(1)`, `today(1)`, and `timeOfDay(1)`.

`QA-002` MEDIUM: native accepted invalid `trace()`/`trace(1)`/extra-argument
trace calls, and fallback accepted zero-argument `trace()`.

No issue was logged for JSON null child preservation, nested descendants,
primitive input, or clock stability/type/precision; those passed after focused
verification.

## Validation After Fix

- FP-12 probe: 27 cases, 0 failures
- Focused pytest: `test_tree_utility_parity.py` 5 passed
- Native FHIRPath sqllogictest: 522 assertions passed
- Full conformance: 2822/2822
