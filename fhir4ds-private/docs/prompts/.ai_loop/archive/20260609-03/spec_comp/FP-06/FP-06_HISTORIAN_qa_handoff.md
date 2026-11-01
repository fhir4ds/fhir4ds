# QA Handoff - FP-06 HISTORIAN

Scope: FHIRPath §5.5.1 `iif`, §5.5.2 Boolean conversion, and §5.5.3 Integer conversion.

Spec grounding: HL7 FHIRPath Normative Release v2.0.0. Section 5.5 says conversion functions operate on singleton collections and multi-item input signals an error. Section 5.5.1 defines `iif(criterion, true-result [, otherwise-result])` and requires short-circuit branch evaluation. Sections 5.5.2 and 5.5.3 define zero-argument `toBoolean()`, `convertsToBoolean()`, `toInteger()`, and `convertsToInteger()` conversion functions with the accepted Boolean lexemes and Integer regex `(\\+|-)?\\d+`.

Probe: `.temp/qa/fp06_historian_probe.py` compares native C++ DuckDB extension and forced Python fallback in isolated subprocesses. It covers `iif` true/false/empty criteria, omitted otherwise branch, lazy unselected branches, fluent `$this` context, malformed `iif` arity, multi-item criterion/input, all accepted Boolean string/integer/decimal lexemes, invalid Boolean strings, Integer signs/range/regex cases, empty propagation, multi-item converter input, and wrong converter arity.

Findings:

- `QA-001` MEDIUM: Native C++ accepts malformed `iif` calls. `iif(true)` and `iif(1|2, 'yes', 'no')` validate true, and `iif(true, 'yes', 'no', 'extra')` returns `"yes"`, while forced fallback rejects them.
- `QA-002` MEDIUM: Native C++ ignores extra args for zero-argument `toBoolean()`/`toInteger()` calls, and forced Python fallback does not raise on constant multi-item converter input for `fhirpath_is_valid()` parity.

No source files were modified during QA. Proceed to remediation with focused native/fallback parity tests and extension rebuild.
