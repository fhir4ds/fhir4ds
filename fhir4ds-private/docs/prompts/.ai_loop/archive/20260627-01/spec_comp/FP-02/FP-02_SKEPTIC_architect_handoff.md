## Architect Handoff - FP-02 SKEPTIC

Structural health: clean. The remediation is local to the Python fallback public DuckDB UDF boundary and does not alter core FHIRPath evaluator semantics, native C++ behavior, parser behavior, or strict-mode exception propagation. It fixes the class of unknown/unimplemented function invocation errors by handling `NotImplementedError` in `fhirpath_scalar()` non-strict mode, not by special-casing `unknownFunction()`.

Issue summary:
- `QA-001` MEDIUM `SPEC_VIOLATION`: resolved and architect-verified.
- New architectural findings: 0.
- Open non-terminal CRITICAL/HIGH/MEDIUM issues: 0.

QA audit: sufficient. QA used current HL7 FHIRPath §4.2-§4.5 text, tested native C++ DuckDB and forced Python fallback paths, covered null/missing propagation, singleton operator errors, function argument singleton behavior, invocation precedence, and backend diff probing. No `RETRY_QA` required.

Validation reviewed/run:
- `.temp/qa/fp02_skeptic_fresh_probe.py` passed 16/16.
- `.temp/qa/fp02_skeptic_diff_probe.py` passed 19/19 after remediation.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py -q` passed 9/9.
- Engineer and architect full conformance summaries both passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

Recommended fix order: none. This inner launch is clean-exit eligible.
