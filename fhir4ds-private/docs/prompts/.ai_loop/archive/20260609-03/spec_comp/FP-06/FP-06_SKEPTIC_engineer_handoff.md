# Engineer Handoff - FP-06 SKEPTIC

Issue fixed: `QA-001` MEDIUM.

Spec basis: HL7 FHIRPath Normative Release §5.5.2 and §5.5.3 define `convertsToBoolean()` and `convertsToInteger()` as zero-argument conversion functions. §5.5 states conversion functions operate on the input collection; argument-bearing calls are not part of these signatures.

Root cause:
- Python fallback registry allowed a one-argument convenience form for `convertsToBoolean` and `convertsToInteger`.
- Native C++ evaluator did not check these two functions for exact zero-argument arity before dispatch.

Implementation:
- Restricted `fhir4ds/fhirpath/engine/invocations/__init__.py` arity for `convertsToBoolean` and `convertsToInteger` to `{0: []}`.
- Added native arity validation in `extensions/fhirpath/src/fhirpath/evaluator.cpp`.
- Added parity coverage in `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`.
- Added native sqllogictest assertions in `extensions/fhirpath/test/sql/fhirpath.test`.
- Rebuilt the native extension and copied it to `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

Validation:
- FP-06 probe after fix: 30 cases, 0 mismatches, 0 expectation failures.
- Focused pytest: `11 passed`.
- Native sqllogictest: `376 assertions passed`.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

No new issues were discovered during remediation.
