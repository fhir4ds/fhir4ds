# QA Handoff - CQL-21 HISTORIAN Iteration 1

**Personality**: HISTORIAN (Role B — Systematic Spec-Walkthrough)
**Chunk**: CQL-21 — Clinical Operators
**Spec**: CQL 1.5.3 Appendix B Clinical Operators (cql.hl7.org/09-b-cqlreference.html)

## Probe Summary

Fresh HISTORIAN §-by-§ walkthrough of CQL-21 Clinical Operators at the
translator -> DuckDB execution surface. Both native C++ extension and
forced Python fallback were exercised with cross-surface parity
comparison. Probe artifacts at
`/mnt/d/fhir4ds/.temp/qa/cql21_historian_2026_07_02_fresh/probe.py` (57
spec-grounded cases across 3 batteries: AgeIn/CalculateAgeIn family,
Equal/Equivalent Code/Concept, ValueSet operators).

## Results

- **Battery 1 (AgeIn/CalculateAgeIn, 26 cases)**: ALL PASS, zero parity
  diffs. Calendar duration semantics correct including leap-year
  boundaries (@2000-02-29 -> @2021-02-28 = 21, @2024-02-29 = 24),
  anniversary boundary checks, NULL operand propagation, future-birthdate
  -> NULL, Date and DateTime overloads. Weeks/Days/Hours/Minutes/Seconds
  use elapsed-time math (correct per spec). Confirms CQL-21 SKEPTIC
  coverage.

- **Battery 2 (Equal/Equivalent Code/Concept, 23 cases)**: ALL PASS,
  zero parity diffs. Code tuple equality (all 4 fields; missing field
  -> None; both missing -> True). Code ~ code+system only always
  true/false. Concept = order-sensitive + display-sensitive. Concept ~
  non-empty intersection always true/false. Cross-type Code~Concept/
  Concept~Code work. Null-operand -> False for ~ (preserves CQL-02
  HISTORIAN fix). Confirms CQL-02 + CQL-21 SKEPTIC coverage.

- **Battery 3 (ValueSet operators, 8 cases)**: 1 FAILURE found.

## Finding: QA-001 HIGH

**Spec violation**: CQL 1.5.3 Appendix B In (ValueSet) — "If the first
argument is a Concept, returns true if any code in the concept is in the
valueset."

**Reproducer**:
```cql
valueset Vitals: 'http://example.org/fhir/ValueSet/vitals'
define InVSConceptMatch:
  Concept { codes: { Code { code: '8867-4', system: 'http://loinc.org' } } }
    in Vitals
```
Cache contains `(http://loinc.org, 8867-4)`.

**Actual**: False (both backends; parity preserved — same bug)
**Expected**: True per spec.

**Translated SQL**: `in_valueset(json_object('codes', [json_object('code', '8867-4', 'system', 'http://loinc.org')]), 'code', 'http://example.org/fhir/ValueSet/vitals')`

**Root cause**: The Concept JSON shape is `{"codes":[{...}]}` (CQL
Concept representation), not the FHIR-conformant
`{"resourceType":"Basic","code":{"coding":[{...}]}}` shape that
`_synthetic_code_resource` produces for Code. The UDF's `_extractAllCodes`
with path `'code'` cannot navigate to the codes.

In `_code_entries_from_ast` (`_operators.py:3112-3122`), only `Literal`
field values are extracted from `InstanceExpression`. The Concept's
`codes` field parses as `ListExpression` (containing Code
InstanceExpressions), not `Literal`. The Literal-only guard skips it,
leaving `fields['codes']` unset. The function returns `None`, and the
translator falls through to generic JSON translation producing the
non-FHIR `{codes:[...]}` shape.

**Independent of prior CQL-21 SKEPTIC iteration**: SKEPTIC tested
`InVSCode` (Code overload with explicit system — works because each
Code field is a Literal), `InVSString` (String overload — works via
separate path), `InVSConceptMatch` is conceptually possible but the
SKEPTIC probe used a different cache shape that may have masked the bug.
The HISTORIAN walkthrough systematically probed every operator overload
form and revealed the issue.

## NOT A BUG Registry additions

(Confirmations of prior CQL-21 SKEPTIC entries; no new spec-compliance
discoveries in this section.)

- Calendar duration for AgeIn* uses anniversary boundary check; not
  elapsed time. `@2000-02-29 to @2021-02-28` is 21 years (leap day
  collapses to last day of Feb in non-leap year).
- `_calc_months` boundary check correct: month-anniversary boundary
  collapses incomplete months.
- All AgeIn*At operators propagate NULL operands to NULL.
- Equal/Equivalent semantics for Code/Concept tuples and intersections
  match spec exactly.
- ValueSet ExpandValueSet(ValueSet) function form works correctly
  (returns list of code JSON objects).

## Handoff

Phase advances to FIX. The single QA-001 HIGH issue requires a
surgical fix to `_code_entries_from_ast` in
`fhir4ds/cql/translator/expressions/_operators.py` to handle
`ListExpression` in the Concept `codes` field.
