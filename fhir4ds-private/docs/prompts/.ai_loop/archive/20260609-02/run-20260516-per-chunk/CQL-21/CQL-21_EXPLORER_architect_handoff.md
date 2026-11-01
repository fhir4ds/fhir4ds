# Architect Handoff - CQL-21 EXPLORER

## Structural Health

The remediation is structurally sound. CQL clinical terminology dispatch now handles the dynamic FHIR resource/path case before generic SQL fallback, matching the existing architecture that static clinical operands and ValueSet membership are semantic translator concerns rather than raw SQL operations.

## Audit Summary

Golden standard written to `.temp/architect/golden_standard.md`. The implemented change satisfies the relevant invariants: it is spec-grounded in CQL `InCodeSystem`, does not hardcode measure ids/patient ids/clinical code lists, keeps the behavior in the translator layer, escapes the embedded CodeSystem URL before wrapping the FHIRPath expression in a SQL literal, and has execution parity coverage for forced Python fallback and native-loaded DuckDB.

QA quality was acceptable. EXPLORER tested more than happy paths: static and dynamic terminology chains, versioned ValueSet/`ExpandValueSet`, age partial precision, and dynamic Code/Concept equivalence. No `RETRY_QA` is needed.

## Issue Disposition

`QA-001` is architect-verified. No new architectural issues were logged.

## Recommended Fix Order

No further fixes are required for this inner workflow. Future clinical-operator changes should extend the same parity file for dynamic resource paths, especially paths that may resolve to either `Coding` or `CodeableConcept`.
