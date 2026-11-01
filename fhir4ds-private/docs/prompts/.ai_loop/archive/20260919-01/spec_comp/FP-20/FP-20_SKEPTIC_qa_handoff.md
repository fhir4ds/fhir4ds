# QA Handoff — FP-20 SKEPTIC (iteration 1, 2026-08-18)

## Scope
FHIRPath R4 §9 (Environment Variables), §10 (Types and Reflection), §11
(Type Safety), §12 (Formal Specifications). Spec grounding: hl7.org/fhirpath/2018Sep
§9–§12 (R4-ballot FHIRPath; sections map to the launch mandate) plus official
fixtures `tests-fhir-r4.xml` (testVariables, testType groups).

## Method
Probes (all with `PYTHONPATH=/mnt/d/fhir4ds`):
- `.temp/qa/fp20_skeptic2_probe.py` — core engine §9/§10/§11 (37 cases).
- `.temp/qa/fp20_skeptic3_probe.py` — DuckDB native C++ vs forced Python
  fallback dual-path (32 cases): **0 parity diffs**.
- Grammar review: `fhir4ds/fhirpath/parser/FHIRPath.g4` vs official N1
  grammar — conformant; only documented deviations (non-greedy STRING = FP-10
  pin; LONGNUMBER CQL superset). `externalConstant : '%' (identifier|STRING)`
  matches official.

## Verified-clean
- %context = ORIGINAL node (spec §9): preserved through select/where focus
  changes on core engine AND both DuckDB paths (name.select(%context.id) → p1).
- %ucum/%sct/%loinc defined (official testVariables1-4 semantics); backtick
  %`name`, single-quote %'name', hyphenated terminology vars all resolve.
- %resource/%rootResource supplied by DuckDB UDF host layer on both paths;
  core evaluate() leaves them host-supplied (spec extension point).
- type().namespace/.name correct across System/FHIR namespaces, quantities,
  times, ofType chains, delimited FHIR.`Patient` (fixtures testType1-23).
- §11 recap: multi-item singleton ops error (core) / classify empty (UDF),
  equality false on repeats, indexers safe — matches doctrine.
- Wrong arity type()/as/is/ofType and unresolved type specifiers rejected
  (is_valid False, both engines agree).

## Findings (all LOW)
- QA-001 INTENDED GAP: §10 metamodel fields (SimpleTypeInfo.baseType,
  ListTypeInfo.elementType, ClassInfo.element, TupleTypeInfo) unimplemented —
  type() exposes {namespace,name} only, consistent across engines, no fixture
  coverage. Recommend status INTENDED + AGENTS.md doctrine entry.
- QA-002 DOC_ERROR: context.py docstrings claim %context "changes with focus";
  behavior is spec-correct (original node). Fix docstrings.
- QA-003 DOC_GAP: undefined env var → ValueError (core) / empty + is_valid
  true (UDF, both paths). Spec leaves this open; document as intended.
- QA-004 TOOLING: `.temp/qa/fp20_skeptic_probe.py` (earlier session) has stale
  is_valid=False expectations for env-var expressions; fails at '%unknown'.

## Handoff to Remediation
Apply QA-002 docstring fix, QA-004 probe fix, add focused regression test
pinning %context-original semantics + type() shape + undefined-env-var UDF
behavior (dual-path). Mark QA-001/QA-003 INTENDED with AGENTS.md notes.
No CRITICAL/HIGH/MEDIUM issues; clean-exit eligible at iteration >= 1.
