# Architect Handoff - CQL-16 EXPLORER

## Golden Standard
Golden standard invariants were refreshed in `.temp/architect/golden_standard.md`. The relevant invariant for this fix is that translated dynamic/resource interval optimizations are allowed only when they preserve the same CQL interval uncertainty semantics as the public helper surface and do not special-case measures, fixtures, or resource IDs.

## Audit Result
No new architecture issues were found. The remediation is scoped to `OperatorsMixin` interval translation and keeps the CQL semantic boundary inside the translator, where precision-qualified overlap lowering already lives. It does not add measure-specific logic, does not inspect CMS IDs or terminology, does not bypass FHIRPath accessors, and does not replace public helper semantics with a separate runtime path. The raw-peer extraction is generic over `SQLInterval`, `intervalFromBounds(...)`, and CASE-wrapped interval expressions.

## QA Audit
QA was sufficient for EXPLORER. It tested translated CQL and public helper surfaces across forced Python fallback, native-loaded registration, and no-Python/browser-style C++; it included nested set-operation output, half-open boundaries, partial temporal precision, incompatible Quantity dimensions, dynamic FHIR scalar/Period choice values, and DQM regression attention. No `RETRY_QA` flag is warranted.

## Handoff Compression
QA found one high-severity spec violation: dynamic FHIR partial temporal point values such as `Observation.effectiveDateTime: "2014"` returned `false` for day-precision overlap instead of SQL NULL. Engineering fixed it by adding a narrow runtime precision guard around the existing decomposed overlap SQL, using raw interval low/high peers so finite partial points become unknown while active unbounded clinical intervals keep evaluating. Validation passed the EXPLORER probe, interval part 2 parity 6/6, official interval operators 412/412, broader interval/WASM parity 28/28, CMS135 100%, and full conformance 2822/2822.

## State
`QA-001` is verified. The workflow is eligible for clean exit after `evolution.json` is updated with `workflow: null` and `exit_reason: CLEAN`.
