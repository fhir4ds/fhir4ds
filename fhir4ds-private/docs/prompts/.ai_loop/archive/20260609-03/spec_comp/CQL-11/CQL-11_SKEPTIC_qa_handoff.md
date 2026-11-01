# QA Handoff: CQL-11 SKEPTIC

Scope: CQL Arithmetic Operators Part 2: Maximum, Minimum, Modulo, Multiply, Negate, Precision, Predecessor, Power, Round, Subtract, Successor, Truncate, TruncatedDivide.

Spec checked: CQL Logical Specification v1.5.3 arithmetic section. Relevant semantics: arithmetic overflow/unrepresentable results are null; Quantity predecessor/successor subtract/add 1 when the quantity is integer-valued and 1e-8 when decimal-valued; Quantity JSON value must be numeric, not a string.

Fresh probe: `.temp/qa/cql11_skeptic_probe.py`.

Hypotheses tested:
- Quantity predecessor/successor might bypass strict Quantity parsing.
- Integer Quantity predecessor/successor might use the Decimal 1e-8 step.
- Round negative ties might inherit DuckDB half-away behavior.
- Power/Div/Mod might leak infinity/errors or divide-by-zero failures.
- Temporal predecessor/successor might lose partial precision.
- Dynamic FHIR numeric-only operators might accept `valueString`.

Findings:
- `QA-001` HIGH: integer Quantity predecessor/successor use 1e-8 instead of 1 across forced Python, native-loaded, no-Python C++, and translated CQL for `1 'cm'`.
- `QA-002` HIGH: forced Python/native public `predecessorOf` and `successorOf` coerce malformed Quantity JSON numeric strings such as `{"value":"5","code":"mg"}` instead of returning SQL NULL.

Non-findings from this pass: Round negative ties, invalid Power, zero Mod/Div, temporal partial precision, unit-converting Quantity modulo/div, and dynamic FHIR valueString numeric-only operations matched expected behavior in the fresh probe.
