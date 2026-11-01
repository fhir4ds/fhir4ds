# QA Handoff - CQL-04 SKEPTIC

## Scope

Fresh independent audit of CQL logical operators: `And`, `Implies`, `Not`, `Or`, and `Xor`. Archived `spec_comp/**` outputs were not inspected.

## Spec Basis

- CQL 1.5.3 Developer's Guide Table 3-F: logical precedence from higher to lower is `and`, then `or`/`xor`, then `implies`; operators in the same category are left-to-right.
- CQL 1.5.3 Logical Specification: logical operators use three-valued Boolean semantics. `implies` returns true for false left operands and for null-left/true-right, otherwise null where information is missing.
- CQL type system: operator operands must match declared operand types; Boolean logic should not be treated as numeric/string truthiness in translated CQL.

## Hypotheses Tested

1. `implies` may be parsed with the wrong precedence relative to `and`/`or`/`xor`.
2. `or` and `xor` may be incorrectly split into distinct precedence levels instead of sharing left-to-right disjunction precedence.
3. Native-loaded DuckDB registration and forced Python fallback may disagree for logical truth tables.
4. Direct DuckDB helper/macro calls may accept non-Boolean values through DuckDB coercion.
5. Measure-facing translated definitions may propagate a parse error before backend execution, affecting both registration paths equally.

## Findings

### QA-001 - HIGH - Logical Precedence Is Wrong

Reproducer:

```cql
define AndImplies: false and false implies false
define OrImplies: true or true implies false
define XorImplies: true xor true or true
```

Observed translation/execution before remediation:

- `AndImplies` translated as `FALSE AND (NOT FALSE OR FALSE)` and returned `false`.
- Expected: `(false and false) implies false`, returning `true`.
- `XorImplies` is similarly vulnerable because CQL places `or` and `xor` in the same precedence category with left-to-right associativity.

Native-loaded and forced Python fallback DuckDB connections matched each other, confirming the bug is in parser/translation shape rather than backend registration.

## Recommended Remediation

Update `fhir4ds/cql/parser/parser.py` so:

- `parse_expression()` starts at implication.
- `parse_implies_expression()` consumes disjunction operands.
- `parse_or_expression()` handles `or` and `xor` in one left-to-right loop.
- `parse_and_expression()` consumes equality operands directly.

Add focused regression tests that translate and execute the affected expressions on both native-loaded and forced Python fallback DuckDB connections.
