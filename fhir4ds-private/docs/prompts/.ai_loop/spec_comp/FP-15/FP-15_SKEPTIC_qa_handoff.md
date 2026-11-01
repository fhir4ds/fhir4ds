# QA Handoff — FP-15 SKEPTIC (§6.3 Types is/as)

## Verdict: CLEAN — zero defects (32 fresh dual-path cases; 2 MISS adjudicated via fixtures)

System is-types (Integer/Decimal/String/Boolean/Date/DateTime/Time true + false rows
+ is(type) spelling parity); FHIR types (gender is FHIR.string SUBTYPE-based, name.first()
is FHIR.HumanName, active is FHIR.boolean, contained Organization, Quantity literal,
unknown-type empty); as passthrough/mismatch/both spellings/as+navigate; System-vs-FHIR
namespace split (active is Boolean false); empty+multi-item propagation; compositions.

Adjudications (both engines IDENTICAL): (1) `Patient is FHIR.Patient` → ['true'] — root
focus IS the resource (my [] expectation wrong). (2) `gender as FHIR.string` → [] —
fixtures :1511-1514 pin as-ofType EXACT-match on the DECLARED primitive type (gender
declared code → as(FHIR.string)/as(string) mismatch; as(code) → male; ValueSet.version
declared string → as(string) KEPT). The is/as asymmetry: is is subtype-based, as/ofType
exact — fixture-pinned doctrine.

Evidence: .temp/qa/speccomp2/fp15_skeptic_probe1.py
