# FP-10 Golden Standard

Architectural invariants for FHIRPath string transform behavior:

1. Public FHIRPath behavior must be spec-grounded at the evaluator boundary,
   not inferred from host-language defaults.
2. Python fallback and native DuckDB/C++ evaluators must expose the same public
   semantics for supported FHIRPath functions.
3. Function signature metadata must move together across invocation registry,
   public validity checks, native arity checks, and tests.
4. `fhirpath_is_valid()` validates expression form and statically knowable
   invalid literals or signatures; dynamic resource-dependent type failures
   remain row-resilient public evaluation failures.
5. Regex safety guards must remain centralized and must apply before
   compiling user-supplied regex patterns in both Python and C++ paths.
6. Regex flags must be validated explicitly. Unsupported flag characters must
   not be ignored silently.
7. UTF-8/Unicode scalar behavior must be preserved in string functions and
   regex dot normalization; native byte-oriented regex behavior must not leak
   through public APIs.
8. Native extension changes must be reflected in the bundled package extension
   and repository copy, with hash equality verified.
9. Focused tests must compare native-loaded DuckDB and forced Python fallback
   paths for every changed public behavior.
10. Native-specific behavior must have sqllogictest coverage so the C++ path is
    validated independently from Python test helpers.
