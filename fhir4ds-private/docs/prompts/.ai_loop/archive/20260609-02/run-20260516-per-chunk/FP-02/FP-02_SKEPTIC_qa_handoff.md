# QA Handoff - FP-02 SKEPTIC

## Scope

FHIRPath §4.2 Operators, §4.3 Function Invocations, §4.4 Null and Empty Propagation, and §4.5 Singleton Evaluation of Collections.

## Strategy

Built a focused native C++ vs forced Python DuckDB fallback matrix in `.temp/qa/fp02_skeptic_probe.py` covering:

- Empty collection operands with arithmetic, concatenation, union/combine, membership, and containership.
- Function invocation on constants and collection projections.
- JSON null/missing field behavior.
- Singleton Boolean evaluation of non-Boolean singleton and multi-item operands.

Normative source checked: FHIRPath Normative Release v2.0.0 §4.2-§4.5 and §6.5.

## Findings

### QA-001 - Python fallback rejected valid empty collection RHS after literal operators

Expressions `'x' & {}` and `'x' + {}` are valid FHIRPath expressions using the empty collection literal. Native C++ returned `['x']` and `{}` respectively; Python DuckDB fallback raised `FHIRPathSyntaxError`.

Root cause hypothesis: fallback malformed-expression validation stripped string literals before checking for leading binary operators.

### QA-002 - Singleton Boolean evaluation drift

FHIRPath §4.5 says a single non-Boolean node supplied where Boolean is expected evaluates as true. Native C++ and Python fallback diverged:

- `active and gender`: native returned true, Python fallback returned the raw string `female`.
- `gender or false`: native returned true, Python fallback returned empty.
- `gender.not()`: Python fallback returned false, native returned empty.

Root cause hypothesis: Python logical operators had inconsistent operand typing; native `not()` rejected non-Boolean singleton input.
