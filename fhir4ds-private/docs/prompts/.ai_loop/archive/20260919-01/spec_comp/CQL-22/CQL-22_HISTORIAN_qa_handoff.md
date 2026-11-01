# QA Handoff — CQL-22 HISTORIAN launch (iteration 1)

Chunk: CQL 1.5 Errors and Messaging — Message(source, condition, code, severity, message).
Personality: HISTORIAN (spec-compliance verifier). Spec verified against the published
Appendix B normative text (Errors and Messaging — Message), fetched live this session:
signature, source pass-through of any type, condition-true gating, code as token,
severities Trace/Message/Warning/Error with ONLY Error stopping evaluation, default
severity Message when severity omitted.

Strategy per mandate: used institutional memory (CQL-22 SKEPTIC archive) to avoid
re-running old probes, and hunted NEW divergences on previously unprobed axes.

## New probes (all on BOTH python-fallback and C++-backed connections; identical results)
- Nested-expression contexts: `1 + Message(2, true, 'E', 'Error', 'boom')` raises; Message
  inside list constructor raises; Message as iif ELSE branch (not taken) does not raise;
  Message inside Coalesce raises when condition true + Error.
- Chained Message(Message(5,...Warning...), ...Error...) raises with the OUTER code ('B').
- Severity case variants at runtime: 'error', 'ErRoR' raise (case-insensitive macro);
  'Trace'/'Message'/'Warning'/'Fatal' pass source through.
- Condition edges: `1 = null` (null condition) -> no processing, returns source 5;
  `1 = 2` (static false folded) -> returns source.
- Structured sources: Tuple source, Interval[1,5] source — Error raises on both paths
  (pass-through path exercised through the macro on both).
- Query contexts via population SQL: Warning-severity Message in a where clause does not
  stop evaluation (source `true` passes through; the operator returns source, not the
  condition — matches spec "result of the operation is the input source"); Error severity
  in where / return / let clauses raises with 'E: prelim found' on both paths.
- Aggregate over Message elements: Sum({Message(1,false,...),Message(2,false,...)}) = 3
  exact DECIMAL(38,8) on both paths.
- Unresolved-identifier severity lowers to the generic getvariable fallback (consistent
  with the translator's identifier mechanism, not a Message-specific silent fallback).

## Findings
- Zero new CRITICAL/HIGH/MEDIUM issues. Implementation remains fully conformant.
- QA-001 (LOW, INTENDED, carried from SKEPTIC): informational Trace/Message/Warning
  channel unimplemented by design (no logging sink in translate-to-SQL); fixtures 4/4.
- QA-002 (LOW, UNCONFIRMED, observation): raised error text format 'code: message' is
  engine-defined; null code yields leading ': ' separator. Spec/fixtures do not pin the
  error text; cosmetic only.

## Validation
- test_message_parity.py 12/12.
- Master gate: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706
  (CqlErrorsAndMessagingOperatorsTest.xml 4/4), DQM 47/47 — OVERALL 2832/2832 (baseline
  holds; DQM passed first pass, no REV-009 retry needed).
- Binaries md5: cql.duckdb_extension c5b22d58310c1eb7bafa17ce7877f989 (repo ==
  ~/.local site-packages), fhirpath 57d0634b6ee6eddee9fc06a1355bef5a.
