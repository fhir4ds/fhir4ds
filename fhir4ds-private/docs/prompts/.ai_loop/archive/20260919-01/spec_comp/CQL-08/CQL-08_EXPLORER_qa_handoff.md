# QA Handoff — CQL-08 EXPLORER (3rd personality launch, iteration 1)

**Personality**: EXPLORER. **Chunk**: CQL 1.5 Nullological Operators (Coalesce, IsNull, IsTrue, IsFalse).
Spec verified live against cql.hl7.org Appendix B §Nullological Operators (Coalesce: "static type of the first argument determines the type of the result"; IsNull: "true iff the argument evaluates to null") and Table 9-E (Date→DateTime implicit).

## Probes (all dual-path: python-only vs native cpp; parity held on every case)
Workspace: `.temp/qa/cql08_explorer3_2026_08_21/` (probe1–probe3).

- **probe1 — mixed-type operands + division guards + literal lists**: Ratio/Quantity/Concept/Code/Date/DateTime Coalesce; IsNull(ToQuantity(bad))/IsNull(ToDate(bogus)) → true; IsNull(ToQuantity('5 mg')) → false; Coalesce(1/0,5), Coalesce(1.0/0.0,5.5), nested Coalesce/0.0 guards → fallback (division-by-zero nulls feed Coalesce correctly); IsTrue(1/0 > 0) → false; IsNull({})→false, IsNull(null as List<Decimal>)→true, IsNull({null})→false, Coalesce({},'fb')→{} (element semantics). All correct, parity OK.
- **probe2 — query-valued lists, postfix chaining, case stacks**: `.isNull()` postfix == infix; Coalesce(...).isNull() chains; case/when over IsTrue/IsFalse/IsNull stacks; where-clause null-comparison filters + Count → 0. **Found QA-001**: IsNull over query-valued expressions (empty query, where-filtered-to-empty, all-null-element query) returns **true**; spec says a query returns a List and an empty list is not null (IsNull({}) is correctly false on the literal path). Same defect mirrored in `is not null`.
- **probe3 — retrieves end-to-end (population SQL over real FHIR resources)**: Coalesce(Patient.birthDate.value,'unknown'); Patient.deceasedBoolean.isNull(); Coalesce over FHIR Boolean default; Coalesce((O.value as FHIR.Quantity).value, 0.0) in return projections; IsNull(first(...)); count([Observation] where IsTrue(status='final')); Coalesce(Patient.multipleBirthInteger/0, 42); define-alias chains (Coalesce(BirthDateVal, ...)). All 9 columns correct on both patients, py==cpp exactly.

## Issues
- **QA-001 MEDIUM CONFIRMED** — IsNull over query-valued (List-typed) operands: empty query list collapses to SQL NULL via scalar-subquery lowering → IsNull=true / is-not-null=false; spec: list ≠ null → false/true. Reproducer: probe2.py IsNullQueryEmpty/IsNullWhereResult.
- **QA-002 LOW INTENDED** — Coalesce(@Date, DateTime(...)) returns the Date-form string; engine unifies Date/DateTime in one partial-precision string space (ToDateTime(Date) is identity), so no observable value deviation; static-type nuance only. Pinned INTENDED.

Prior SKEPTIC/HISTORIAN fixes re-verified intact (variadic Coalesce, uniform String/numeric type-family error, nested Coalesce static typing, Decimal conversion reverts).
