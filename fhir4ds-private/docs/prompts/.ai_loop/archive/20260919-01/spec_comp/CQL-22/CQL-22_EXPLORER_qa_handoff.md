# QA Handoff — CQL-22 EXPLORER launch (iteration 1)

Chunk: CQL 1.5 Errors and Messaging — Message(source, condition, code, severity, message).
Personality: EXPLORER (fuzzer/abuser). Probes in .temp/qa/probe_cql22_explorer.py and
probe2.py (both engine modes: Python fallback and C++ extension; identical results
throughout — the defect found is translation-level, shared by both).

## Probe axes (per mandate)
- Message in where clauses of define-alias chains and aliased retrieves: retrieve-alias
  where raises correctly ('CHK: cond not active') once the precomputed clinical_status
  column exists; population-SQL-shaped defines (exists/Count over guarded retrieves)
  raise/pass correctly on both engines.
- Message source from dynamic FHIR navigation (multi-valued Patient.name.given):
  per-patient raise confirmed via CQLMessage on the flattened list — **but** the
  aliased navigation query form found QA-001 below.
- Nested navigation condition per name-row (`Patient.name N where ... return N.given`):
  **QA-001 (MEDIUM, RESOLVED in FIX phase)** — where clause silently discarded
  (unfiltered results for every patient, Error-severity Message raise swallowed).
  Also reproduced WITHOUT Message → general query-where drop on scalar fhirpath
  sources, not Message-specific; fixed at the shared lowering site.
- Message condition from uncertain age operand: AgeInYearsAt with null birthDate →
  cqlUncertainCompare → null condition → no processing, source returned (spec-correct);
  real-age true conditions raise on both engines.
- Special chars/unicode: embedded quotes (c'd / it's), double quotes, backslashes,
  unicode code (コード) and message (méssage — ✓) all round-trip on warn pass-through
  and Error raise text on both engines; 5000-char code works both ways.
- Message into Message's condition: Warning inner returning its source into outer
  condition raises outer Error (correct — inner Message returns its source); inner
  Error inside a condition raises inner code; false/null inner conditions no-op.
- Population-criteria shapes: Error in denominator-style exists(...) raises; Count
  over never-firing guard OK.
- Prior SKEPTIC/HISTORIAN coverage re-verified intact (parity suite 12/12 pre-fix).

## Findings
- QA-001 MEDIUM SPEC_VIOLATION (open → fixed): see evolution.json.
- QA-002 LOW INTENDED, QA-003 LOW UNCONFIRMED carried from prior launches.
- Observation (out-of-chunk, not logged as blocker): test_audit_mode.py
  TestMinMaxAttribution test_min/max_on_query_uses_arg_{min,max} fail on the
  cumulative uncommitted tree; bisected — failures persist with this launch's
  change disabled, i.e. pre-existing from an earlier launch. Conformance gate
  unaffected (2832/2832). Flag for human review.

## Validation
- test_message_parity.py 13/13 after fix (incl. new dual-engine regression test).
- Master gate fresh on final tree: ViewDefinition 144, FHIRPath 935, CQL 1706,
  DQM 47 — OVERALL 2832/2832 (DQM passed first pass, no REV-009 retry).
