# QA Handoff - CQL-21 EXPLORER

## Scope

Ran fresh EXPLORER probes for CQL-21 Clinical Operators against current source with `PYTHONPATH=.` so local code was tested. Focused on pathological combinations of CodeSystem membership, ValueSet membership/versioning, `ExpandValueSet`, dynamic FHIR `CodeableConcept` equivalence, and partial age precision. Consulted CQL v1.5.3 clinical operator docs: `in (Codesystem)` maps to `InCodeSystem`; `InCodeSystem` returns true when the given code, or any code in a concept, is in the referenced code system.

## Findings

`QA-001` is open. Dynamic CodeSystem membership over a FHIR resource value lowers to invalid SQL:

```sql
fhirpath_text(O.resource, 'code') IN '{"id":"http://loinc.org","name":"LOINC"}'
```

Both forced Python fallback and native-loaded DuckDB reject that SQL with a parser error. A query such as:

```cql
define DynamicCodeInCodeSystem:
  exists ([Observation] O where O.code in LOINC)
```

should lower to a clinical CodeSystem predicate over `O.resource.code` rather than generic SQL `IN`.

## Non-Issues / Observations

Versioned ValueSet references and inline Code selectors in ValueSet membership passed when run against local source. `Count(ExpandValueSet(VitalsV1))` lowered to `list_count(ExpandValueSet(...))` and returned `2` in both backends. Dynamic Code/Concept equivalence with predicates stayed fixed and matched expectations. Partial age precision still returns concrete boundary values; I did not log this because the current public helper surface lacks an uncertainty representation and this probe did not produce a backend divergence.

## Probe

Reproducer script: `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/cql21_explorer_probe.py`

Run command:

```bash
PYTHONPATH=. python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/cql21_explorer_probe.py
```
