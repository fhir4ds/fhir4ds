# Architect Handoff — CQL-05 Structural Type Operators (HISTORIAN, iteration 1)

## Golden-standard invariants applied
1. CQL semantics are driven by the spec text (cql.hl7.org), verified per behavior, not by intuition.
2. Model/type knowledge must be data-driven (inference.fhir_type_names_for_cql_type), never inline
   clinical lists.
3. No silent fallbacks: a query-source alias must never silently bind to the wrong rows; wrong
   SQL shapes must fail loudly at generation or execution.
4. Native C++ and forced-Python paths must agree (parity is asserted in tests).

## Audit of this iteration's fixes
- QA-101 fix is general (any nested-query source with a value projection), spec-grounded (§Query/§As/§Is),
  and preserves data-driven typing via the existing family map — no hardcoded types. The static
  as-cast is-check correctly reduces to `IS NOT NULL` (As nulls on mismatch; `null is T` false) and
  uses `_structural_type_conforms` + the FHIR family map rather than string equality.
- Known fragility (logged, not fixed): the CTE-flatten region in `_translate_query` accumulates
  special cases (union/placeholder/set-op/value-projection); future element-value sources should
  converge on one registration path (`add_alias(table_alias=alias)` + `_alias_source_asts`) and a
  single `_alias_is_element_value` classification instead of per-shape elif chains.
- QA-102 fix is general and recursive (json_array), UDF-agnostic (verified both paths), and adds
  no new UDF knowledge to the translator.
- Pitfall archived in ARCHIVE_LOG: element-value projections must stay single-column; a second
  patient_id column breaks scalar-subquery call sites (cost a 14-measure binder regression that the
  recovery gate caught — process worked as designed).

## QA quality gate
QA (HISTORIAN) was NOT lazy: verified normative text via live spec fetch before logging, probed
both execution paths with parity assertions, re-verified all four SKEPTIC fixes for regression,
and found two NEW divergences beyond the prior launch's probes, one initially suspected behavior
(convert 'yes' to Boolean) was correctly cleared against the spec instead of logged. RETRY_QA: false.

## Issue counts / state
- RESOLVED: 2 (QA-101 HIGH, QA-102 MEDIUM) — tombstoned in evolution.json, details in ARCHIVE_LOG.
- OPEN: 1 (QA-103 HIGH) — pre-existing DQM conformance regression (32/47), bisect-attributed to
  sibling-chunk campaign edits (08-20 05:29-05:40 window), out of CQL-05 scope. Recommended Fix
  Order for the outer orchestrator: (1) assign QA-103 to the owning session; the failing pattern
  is at tests/output/sql/CMS117.sql:262 — a set-op branch operand (SELECT patient_id, resource FROM
  <CTE>) is passed as fhirpath_text's scalar resource argument inside CROSS JOIN LATERAL; (2) that
  session must re-run the full gate (PROC_VALIDATION.md) before handoff — this launch found the
  gate claim "2832/2832" was stale, indicating gate runs are not being repeated after late fixes.

## Handoff compression
QA found 2 new chunk divergences (as-cast alias binding, nested-list traversal serialization);
engineer fixed both root causes in the translator with parity regression tests (19/19); suites
ViewDef 144/144, FHIRPath 935/935, CQL 1706/1706 hold; DQM 32/47 is a pre-existing,
bisect-attributed foreign regression left OPEN for the outer orchestrator.
