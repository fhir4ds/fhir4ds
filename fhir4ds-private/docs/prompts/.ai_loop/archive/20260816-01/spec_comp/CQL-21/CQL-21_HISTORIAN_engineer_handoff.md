# Engineer Handoff - CQL-21 HISTORIAN Iteration 1

## Scope

Single open issue: **QA-001 HIGH** — Concept-in-ValueSet with inline Concept
literals always returned False even when a matching (system, code) pair was
loaded into the cache.

## Triage

- Category: SPEC_VIOLATION
- Severity: HIGH
- Confirmed: Yes — reproducer in
  `/mnt/d/fhir4ds/.temp/qa/cql21_historian_2026_07_02_fresh/probe.py`
  returned False on both Python fallback and C++ extension (parity
  preserved — same bug class).

## Reproducer

```cql
valueset Vitals: 'http://example.org/fhir/ValueSet/vitals'

define InVSConceptMatch:
  Concept { codes: { Code { code: '8867-4', system: 'http://loinc.org' } } }
    in Vitals
```

Cache contains `(http://loinc.org, 8867-4)`.
Expected: `True`. Actual: `False` on both backends.

## Root Cause

The translator's static-extraction helper `_code_entries_from_ast` in
`fhir4ds/cql/translator/expressions/_operators.py` (the local function
inside `_translate_in_op`) only inspected `Literal` field values when
walking an `InstanceExpression`. For a `Concept { codes: { Code { ... } } }`
instance, the `codes` field parses as a `ListExpression` containing
`InstanceExpression`s (one per Code), not a `Literal`. The Literal-only
guard skipped it, leaving `fields['codes']` unset, so the function
returned `None` and the translator fell through to the generic
`_translate_instance_expression` path which produces a CQL-Concept JSON
shape `{"codes":[...]}` instead of the FHIR-conformant
`{"resourceType":"Basic","code":{"coding":[...]}}` shape that
`_synthetic_code_resource` produces for Code literals.

The downstream `in_valueset` UDF's `_extractAllCodes` walks the resource
JSON using the supplied FHIR path. With path `'code'`, it cannot find a
`code` field at the top level of `{"codes":[...]}`, so it returns an
empty list and the UDF returns False.

This bug is independent of the prior CQL-21 SKEPTIC iteration because
SKEPTIC tested the Code overload (each Code field IS a Literal, so the
old code path worked), the String overload (separate path), and a
Concept overload against a different cache shape that happened to mask
the bug. The systematic HISTORIAN walkthrough of every operator
overload form revealed the gap.

## Fix

Surgical change to `_code_entries_from_ast` in
`fhir4ds/cql/translator/expressions/_operators.py` (around line 3112).
Added a branch that detects when the Concept's `codes` element parses
as a `ListExpression`, recurses into each Code via the existing
`_code_entries_from_ast` recursion, and collects the resulting code
entries into `fields['codes']`. The rest of the function unchanged.

The upstream logic in `_translate_in_op` then correctly uses
`_synthetic_code_resource` per Code entry and OR-chains the
`in_valueset` calls for multi-code concepts.

## Regression Coverage

Added `test_cql_concept_in_valueset_with_literal_codes_matches_per_spec_cql21_historian`
in `fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py`
(4 cases x 2 backends):
- `ConceptSingleMatch`: single-code Concept matching cache -> True
- `ConceptMultiAnyMatch`: multi-code Concept, any match -> True (OR-chain)
- `ConceptMultiNoMatch`: multi-code Concept, no match -> False
- `ConceptSingleNoMatch`: single-code Concept, no match -> False

## Verification

- New regression test PASSES on both Python fallback and C++ extension.
- All 29 tests in `test_clinical_operator_parity.py` and
  `test_clinical_type_parity.py` PASS.
- Full conformance 2822/2822 = 100% (ViewDefinition 134/134, FHIRPath
  935/935, CQL 1706/1706, DQM 47/47). ZERO regressions.
- The 4 pre-existing failures in `test_primitive_parity.py` and
  `test_string_operator_parity.py` remain pre-existing (verified by
  re-running on dev before my change). All unrelated to clinical
  operators.

## Side Discoveries (NOT fixed - out of scope)

1. The `expand Vitals` operator form (interval-list expansion with a
   ValueSet argument) silently translates to a temporal/list `expand1`
   UDF call returning empty. Per CQL spec, there is no standalone
   `expand <ValueSet>` operator; the correct form is the function
   `ExpandValueSet(VS)`. The function form works correctly. The parser
   silently accepting `expand Vitals` is a separate tolerance question
   for human review (NOT a CQL-21 clinical operator bug).
