# QA Handoff - CQL-01/HISTORIAN

## Scope
CQL primitive types: Any, Boolean, Integer, Decimal, String, Long. HISTORIAN pass traced the official CQL 1.5.3 primitive type rules, parameter default semantics, SKEPTIC lexer fixes, primitive `is`/`as`, and native-loaded vs forced Python fallback behavior.

## Finding
- QA-001 HIGH: scalar primitive parameters with defaults lose both the default value and declared type metadata when lowered to SQLParameterRef/getvariable. `parameter P Integer default 5` evaluates as an empty VARCHAR when unset, so `P is Integer` is false, `P is String` is true, and arithmetic such as `P + 1` fails binding.

## Reproducer
See `.temp/qa/cql01_historian_probe.py` after remediation for the retained regression matrix.

## Spec Basis
CQL parameters may have compile-time defaults and may be referenced by name in expressions; primitive `is`/`as` must operate on the actual CQL type, not on the string transport used by DuckDB session variables.
