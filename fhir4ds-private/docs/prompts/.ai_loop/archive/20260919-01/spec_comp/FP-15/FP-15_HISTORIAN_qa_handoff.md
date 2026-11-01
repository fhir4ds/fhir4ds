# QA Handoff — FP-15 HISTORIAN launch (2026-08-18)

Chunk: FHIRPath §6.3 Types — `is`/`as` type specifiers (infix + functional forms).
Personality: HISTORIAN. Probes: `/mnt/d/fhir4ds/.temp/qa/fp15_historian_2026_08_18/probe{,2,3,4,5}.py`
(78-case dual-path main probe + targeted drills; native extension vs forced Python
fallback, both via `SELECT fhirpath(?::JSON, ?)`).

## What was probed (NEW angles beyond SKEPTIC)
- SKEPTIC's 5 fixes re-verified regression-free: hierarchy merge (`valueUuid is
  FHIR.uri/FHIR.string`, `oid→uri→string` all true), native `5 'mg' is
  FHIR.Quantity` EMPTY, `contained is/as(Patient)` correct on fallback,
  `5 'mg' is Quantity` → true with a real resource focus, typecheck helpers clean.
- Multi-level ancestors for `is` (…is FHIR.Element / Resource / DomainResource /
  BackboneElement): clean both engines (HumanName correctly NOT BackboneElement).
- False-vs-empty `is` semantics on literals and FHIR values with real resource
  focus: clean (non-match → false, absent → empty, both forms).
- String-literal type args `is('Patient')` → Unknown type error → [] on both: clean.
- Real choice fields (Observation.value[x], Condition.onset[x], Patient.deceased[x]):
  clean. Quantity assertion chains (`(value as Quantity).unit`) clean.
- System-vs-FHIR namespace cross checks: clean (incl. `multipleBirthInteger is
  System.Integer` false, `valueQuantity is System.Quantity` false).
- Multi-item focus → [] identically (shared udf error-swallow convention).
- Backtick dotted spellings, infix and functional, with `as` navigation: clean.
- NULL-resource literal eval returns EMPTY on both (udf contract, harness-level).

## Issues filed
- QA-001 HIGH OPEN — dual-engine: `as` ignores subclass semantics for FHIR
  primitive specifiers. `(gender as FHIR.string)='male'` → [] on BOTH engines
  while `gender is FHIR.string` → true (§6.3: as returns value "if it is of the
  type specified, or a subclass thereof"). Also `id as FHIR.string`,
  `valueUuid as FHIR.uri/FHIR.string`, `valueCode as FHIR.string`. Fallback:
  primitive-exact branch in `engine/invocations/types.py as_fn`. Native:
  `fn_asType` forces `exact=true` via `isFHIRPrimitiveTypeName(target)`
  (evaluator.cpp ~11100). No fixture pins the exact-match doctrine (only
  `(Observation.value as Quantity).unit`, complex type).
- QA-002 MEDIUM OPEN — fallback types `Patient.implicitRules` as FHIR.string
  (value-shape inference); native types it uri (curated `fhirFieldType`).
  `implicitRules is FHIR.uri` → native true / fallback false. Missing entry in
  `fhir4ds/fhirpath/models/r4/fhir_path_to_type.json` (has `.system`,
  `.valueUri` → uri).
- QA-003 LOW INTENDED — `abatementBoolean` is not a valid R4 Condition field
  (abatement[x] = dateTime|Age|Period|Range|string); native's generic
  `abatement*` key scan accepts it, fallback metadata-strictly returns empty.
  Non-conformant input; documented, no fix.

## Verified clean / NOT A BUG
- All literal `is`/`as` System specifiers with a real resource focus (the
  SKEPTIC-era "EMPTY on literal" observations were a NULL-resource harness
  artifact; both engines agree).
- `instantiatesUri` typed uri on fallback (choice-suffix inference), `.system`,
  gender/language/use → code, city/state → string: parity held.

Handing off to Remediation Engineer: fix QA-001 (both engines + extension
rebuild + parity tests) and QA-002 (metadata entry + regression test). Baseline
2832/2832 must hold.
