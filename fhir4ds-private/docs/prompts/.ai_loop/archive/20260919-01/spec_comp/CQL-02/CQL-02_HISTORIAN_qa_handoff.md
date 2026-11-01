# QA Handoff — CQL-02 (CQL 1.5 Types — Clinical), iteration 1, HISTORIAN (2026-08-19)

## Method
Fresh execution-level probing (translate_cql per-definition SELECT) on BOTH Python
fallback and native C++ registrations, spec-grounded against CQL 1.5 structured-type
definitions (Code/CodeSystem/Concept/ValueSet/Vocabulary) and terminology-operator
doctrine. Probe: `.temp/qa/cql02_historian_2026_08_19/probe.py` (60 cases) plus two
follow-up membership probes in the same session. Note: register with
`include_fhirpath=True` — `Concept { } ~ ...` and `.codes` navigation lower to
fhirpath helpers.

## SKEPTIC-fix re-verification (all intact, 0 parity diffs)
- `~` case/locale-insensitive on code+system (CodeEquiv*, AliasCaseEquiv all true)
- Concept { codes: { NamedCode } } folding: NamedCodesFoldCount=2
- `.codes` List<Code>: CodesAccessorCount=2, First(codes).code works
- static clinical define-alias inlining: AliasEquiv/AliasCount/CodeDef/ConceptDef OK
- Vocabulary is/as hierarchy, as-Any subtype retention (VSAsVocIsValueSet etc.) OK

## Verified clean (new areas)
- Versioned codesystem `code X: 'c' from CS version '2.74'`: .version/.system correct
- CodeSystem equality/equivalence incl. same-id-different-name → false (tuple semantics)
- Concept tuple equality: display null-vs-given → null; both-no-display → true;
  codes order-sensitive for `=`, order/case-insensitive intersection for `~`
- Empty Concept: `Concept { } ~ Concept { }` → true; `~ non-empty` → false;
  `Count((Concept { }).codes)` → 0; `Concept { codes: {} } in CS` → FALSE
- ValueSet/CodeSystem typed defines materialize structured JSON; `is` checks work
- List<Code>/List<Concept> equivalence case-insensitive transit OK
- `null in VS`, `null as Code in VS` → false (both backends)

## Issues (see evolution.json)
- QA-001 HIGH: ValueSet/CodeSystem **define-alias** membership (`X in VSDef`,
  `X in CSDef`) and `ExpandValueSet(VSDef)` do NOT unwrap the structured clinical
  JSON back to the canonical URL → `... IN '{"id":...}'` ParserException (both
  backends); ExpandValueSet receives the JSON blob as URL arg.
- QA-002 HIGH: `Concept { } in LOINC` emits `json_object() IN '<CS JSON>'` —
  invalid SQL on both backends (empty-concept member falls into generic list-IN path
  with a CodeSystem operand). `Concept { codes: {} } in LOINC` is fine.
- QA-003 MEDIUM: Python-fallback `in_valueset` RAISES through DuckDB when value-set
  data is not loaded, while native C++ returns SQL NULL — parity + row-resilience
  violation (root: raise in fhir4ds/cql/duckdb/udf/valueset.py / system_resolver.py).

## Notes for FIX
- QA-001/QA-002 are translator-layer (`_translate_in_op` / membership unwrap in
  `_operators.py`); shared by both backends → no extension rebuild needed.
- QA-003 is Python-fallback-only (UDF layer); align with native NULL-on-missing-data
  row-resilience; keep DQM loaded-valueset behavior unchanged.
- Add focused dual-backend regression tests to
  `fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py`
  (extend the CQL-02 family), then re-run full conformance (baseline 2832/2832).
