## QA Handoff - FP-02 SKEPTIC

Scope: FHIRPath §4.2 Operators, §4.3 Function Invocations, §4.4 Null and Empty propagation, and §4.5 singleton collection evaluation.

Normative basis checked from the current HL7 FHIRPath source:
- §4.3 defines function invocation over input collections, with chained fluent syntax and a finite listing of supported functions.
- §4.4 states missing or null underlying data produces no node and therefore an empty collection, not a null literal.
- §4.4 says single-input operators/functions generally propagate empty operands or arguments as empty results; collection-taking operations treat empty as an ordinary collection.
- §4.5 says collections passed to singleton inputs convert only if empty, single convertible, or single non-Boolean for Boolean input; multi-item ambiguity signals an error.

SKEPTIC hypotheses tested:
1. Native and forced Python fallback may diverge when invalid function invocations hit public SQL UDF wrappers.
2. JSON null fields or arrays containing null may be surfaced as literal null instead of empty.
3. Operators expecting singleton operands may accidentally use the first item of a multi-item collection.
4. Function arguments expecting singleton values may use the first item of a multi-item path.
5. Fluent invocation precedence around unary operators and dot invocation may route the wrong source collection.

Fresh probes created and run:
- `.temp/qa/fp02_skeptic_fresh_probe.py` passed 16 expected-result cases across native C++ DuckDB and forced Python fallback.
- `.temp/qa/fp02_skeptic_diff_probe.py` found one backend mismatch before remediation: fallback `fhirpath()` throws for `unknownFunction()`.
- Manual isolating SQL confirmed native `fhirpath(..., 'unknownFunction()')` returns `[]`, native/fallback `fhirpath_is_valid('unknownFunction()')` returns `false`, and only forced fallback `fhirpath()` raises `InvalidInputException` wrapping `NotImplementedError`.

Issues:
- `QA-001` MEDIUM OPEN: forced Python fallback `fhirpath()` list UDF leaks `NotImplementedError` for unknown function invocations instead of returning public row-resilient empty output in parity with native.

State:
- `evolution.json.phase` set to `FIX`.
- `fhir4ds/fhirpath/AGENTS.md` updated with the open fragile area.
