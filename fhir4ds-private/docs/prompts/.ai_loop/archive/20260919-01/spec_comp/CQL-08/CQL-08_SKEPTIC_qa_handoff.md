# QA Handoff — CQL-08 SKEPTIC (iteration 1, 2026-08-20)

Chunk: CQL 1.5 Nullological Operators (Coalesce, IsNull, IsTrue, IsFalse).
Spec verified against cql.hl7.org Developer's Guide §Nullological Operators
(fetched live this launch) and the official HL7/cql grammar already cached at
`.temp/qa/cql04_explorer2_2026_08_20/cql.g4`.

## What was probed (dual-path: Python supplements vs C++ native, every case)

- `probe1.out`: 43 expression-level defines — prefix IsNull/IsTrue/IsFalse,
  postfix `.isNull()/.isTrue()/.isFalse()`, infix `is null/is not null/is
  true/is false/is not true/is not false`, IsNotNull, `not IsNull`, Coalesce
  arity/mixing/temporal/list/query forms, null-never-leak Boolean returns,
  Coalesce arithmetic composition, `Coalesce(1/0, 5)` error containment.
- `probe2.py`: end-to-end population SQL over FHIR resources (absent
  `deceasedBoolean`, `active` present/absent, Observation where-clauses with
  `is null` and `Coalesce(O.status, 'unknown')`, expression-level
  null preservation vs the CQL-04 population membership encoding).

## Verified correct (py == cpp throughout)

- IsNull(null)=true; IsNull(non-null)=false; IsTrue(null)=false;
  IsFalse(null)=false — Boolean tests never return null. Prefix == postfix ==
  infix forms. `is not true/false` = NOT of the test.
- Absent FHIR field → IsNull true, IsTrue/IsFalse false,
  Coalesce(field, false) default works; where-clauses filter correctly.
- Expression-level Coalesce(all-null) stays NULL at define level
  (CQL-04 boundary respected).
- Coalesce(1/0, 5) = 5; Coalesce({1,null,3}) = 1; query-list overload works.

## Issues logged

- QA-001 HIGH OPEN — Coalesce scalar arity artificially capped at 5
  (translator `_translate_coalesce` + public UDF); spec is variadic unbounded.
  Six-arg Coalesce raises TranslationError on both paths.
- QA-002 MEDIUM OPEN — order-dependent type mixing: `Coalesce(null,1,'x')`
  returns 1, `Coalesce(null,'x',1)` Binder-errors. Spec: arguments must be
  implicitly castable to a common type (Integer/String are not) — uniform
  rejection expected.
- QA-003 LOW INTENDED — IsTrue/IsFalse accept non-Boolean operands returning
  false (lenient, pinned by tests; no truthiness leak).
- QA-004 LOW INTENDED — IsNotNull function form is a harmless superset
  (spec defines only `is not null` operator).

Probes: `.temp/qa/cql08_skeptic_2026_08_20/` (probe.py, probe1.out, probe2.py).
