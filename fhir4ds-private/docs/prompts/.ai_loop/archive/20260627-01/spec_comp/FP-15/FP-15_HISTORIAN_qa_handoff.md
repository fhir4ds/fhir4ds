# QA Handoff - FP-15 HISTORIAN

## Scope

- Chunk: FP-15, FHIRPath §6.3 Types.
- Personality: HISTORIAN.
- Spec source: HL7 FHIRPath continuous-build source, §6.3 `is` / `as` type specifier and function forms.
- Fresh probe: `.temp/qa/fp15_historian_fresh_probe.py`.

## Probe Coverage

- `is` operator and `is(type)` function over System primitive literals.
- `as` operator and `as(type)` function over matching and mismatching primitive values.
- FHIR primitive namespace behavior: `FHIR.boolean`, `System.Boolean`, `gender is string`, `gender as code`.
- Empty input and multi-item public wrapper behavior.
- Invalid type specifiers, invalid FHIR/System aliases, and wrong arity.
- Direct R4 resource type specifiers intersecting review-10: `CodeSystem`, `QuestionnaireResponse`, `Binary`, `Parameters`.
- Choice-type assertions after `entry.resource.ofType(Observation).value.is/as(Integer)`.

## Finding

`QA-001` MEDIUM `SPEC_VIOLATION` is open.

Evidence from fresh probe:

- `missing is Integer` returned `fhirpath=[]`, `fhirpath_text=NULL`, `fhirpath_bool=NULL`, `fhirpath_is_valid=true` in both native DuckDB/C++ and forced Python fallback.
- `missing.is(Integer)` returned the same.
- Expected under current §6.3: `is` should return `false` for empty input because it is a non-error "all other" case. `as` empty-input behavior remained correct as empty.

## Handoff

Fix both execution paths:

- Python: `fhir4ds/fhirpath/engine/invocations/types.py::is_fn`.
- Native: `extensions/fhirpath/src/fhirpath/evaluator.cpp::Evaluator::fn_isType`.

Do not alter `as` empty-input behavior. Preserve multi-item singleton errors internally and public row resilience externally.
