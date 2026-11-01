# QA Handoff: CQL-10 SKEPTIC

## Scope

Chunk CQL-10, Arithmetic Operators Part 1: Abs, Add, Ceiling, Divide, Floor, Exp, HighBoundary, Log, Ln, LowBoundary.

## Spec Anchor

Verified against the current HL7 CQL Reference v1.5.3:
- Arithmetic operators generally return null for overflow/underflow or impossible operations such as division by zero.
- Quantity is a structured type whose `value` element is Decimal and must be present.
- Add/Divide over Quantity must preserve Quantity semantics and return null for invalid operands.

The bundled official XML conformance suite marks `Exp(1000)` and `Ln(0)` as invalid/runtime-error cases; current project behavior matches that conformance target.

## Hypotheses Tested

1. Python fallback Quantity arithmetic may coerce malformed JSON values through Python `float()`.
2. Dynamic FHIR `valueQuantity` arithmetic may inherit that coercion in translated CQL.
3. Direct public helper surfaces may diverge between native-loaded and forced Python fallback registrations.
4. Numeric-looking `valueString` FHIR choices must not be treated as numeric evidence.
5. Boundary helpers must preserve numeric text, year-only date, and time boundary behavior.

## Finding

`QA-001` HIGH: forced Python fallback accepts malformed Quantity JSON with string or Boolean `value` fields while native registration returns SQL NULL. Reproducer: `.temp/qa/cql10_skeptic_probe.py`.

Initial direct evidence:
- Python fallback `quantityValue('{"value":"10","code":"mg"}')` returned `10.0`; native returned `NULL`.
- Python fallback `quantityAdd('{"value":"10","code":"mg"}', '{"value":1,"code":"mg"}')` returned `11 mg`; native returned `NULL`.
- Python fallback `quantityAdd('{"value":true,"code":"mg"}', '{"value":1,"code":"mg"}')` returned `2 mg`; native returned `NULL`.

The same root parser feeds translated dynamic FHIR expressions including `(O.value as Quantity) + 1 'mg'`, `(O.value as Quantity) / 2`, and `Abs(O.value as Quantity)`.

## Files

- Probe: `.temp/qa/cql10_skeptic_probe.py`
- State updated: `evolution.json`
