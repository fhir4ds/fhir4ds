# QA Handoff — FP-15 fresh SKEPTIC launch (2026-08-18)

Chunk: FHIRPath §6.3 Types — `is`/`as` type specifiers (infix + functional forms).
Personality: SKEPTIC. Probe: `/mnt/d/fhir4ds/.temp/qa/fp15_skeptic2_2026_08_18/probe.py`
(121 dual-path cases, native extension vs forced Python fallback, both through
`SELECT fhirpath(?::JSON, ?)`; fixtures from `tests-fhir-r4.xml` testType*/testTypeA*).

## What was probed
- All fixture anchors (testType5–23, testTypeA1–A4): pass on both surfaces except QA-001.
- System specifiers on literals (Integer/Decimal/String/Boolean/Date/DateTime/Time/Quantity,
  qualified and unqualified, both syntax forms): clean.
- FHIR resource/datatype specifiers incl. subtype chains (Patient/Resource/DomainResource/
  BackboneElement/HumanName/ContactPoint), backtick and FHIR.-qualified spellings: clean.
- FHIR primitives vs System namespace split (testType11–14 doctrine): clean.
- `as` casting + downstream navigation (`(value as Quantity).unit`, `(contained as Patient).id`,
  choice `as FHIR.string/FHIR.Quantity`, non-matching → empty): clean natively; fallback
  hijacked on `contained` (QA-003).
- Empty/absent focus: `{}` and missing fields → empty on both. Multi-item focus: errors →
  empty identically on both (parity only; no fixture).
- Unknown type names (`5 is Bogus` → empty, `as Bogus` → empty): shared convention, both agree.

## Issues filed (see evolution.json)
- QA-001 HIGH OPEN — fallback: `valueUuid is FHIR.uri` false (fixture testTypeA4 true);
  legacy fhir_type_hierarchy.json flattens uuid→string over canonical type2Parent.
- QA-002 HIGH OPEN — native: `5 'mg' is FHIR.Quantity` true; namespace doctrine says false.
- QA-003 HIGH OPEN — fallback UDF: `contained is/as(T)` hijacked by bogus
  `Resource.contained: [containedResource]` single-option CHOICE_TYPES entry in the
  choice-assertion rescue, overriding correct evaluator results.
- QA-004 MEDIUM OPEN — exported helper typecheck.is_type/as_type: unqualified string
  specifiers broken (`5 as Integer` → []); 11th "exported helper API forgotten" instance.
- QA-005 LOW OPEN — grammar corner `X is FHIR.Quantity.not()` native [] vs fallback ['false'].
- QA-006 LOW INTENDED — telecom.system typed uri (name-only metadata limit, REV-002 family).

## Verified clean (do not "fix")
- `id is FHIR.string` → true (id derives from string per R4; both engines).
- `valueQuantity is Quantity` (unqualified) → true on both — shared convention.
- `active as Boolean` → empty (FHIR.boolean ≠ System.Boolean) on both.
- `(1 as Decimal) = 1.0` → empty on both (`as` is an assertion, not conversion; Integer
  is not Decimal).
- `(5 'mg' as Quantity).value` → 5.0 on both (Quantity value Decimal rendering convention).

Handing off to Remediation Engineer.
