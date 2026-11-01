# QA Handoff — SOF-VD-02 (HISTORIAN), iteration 1

## Probed (PYTHONPATH=/mnt/d/fhir4ds; probes in /mnt/d/fhir4ds/.temp/qa/sofvd02_historian/)
Spec-walk of SQL-on-FHIR v2 constants (IG StructureDefinition-ViewDefinition, fetched live: constant 0..*, name 1..1 sql-name, value[x] 1..1 with the 19 primitive choices, "%name ... effectively converts the FHIR literal defined here to a FHIRPath literal"):

1. **Prior SKEPTIC fix re-verified**: out-of-range integer64 constant (9999999999) still raises typed ConstantResolutionError through SQLGenerator.generate. Regression-free.
2. **NEW — decimal literal serialization (probe1/2/3)**: `resolve_constant` serializes decimals via `str(float)`; Python switches to exponent notation for |v| < 1e-4 or >= 1e16. `valueDecimal: 0.00001` (valid FHIR decimal; JSON allows exponents) substitutes to `1e-05`, which is NOT a valid FHIRPath literal — both engines (native extension, loaded via allow_unsigned_extensions, and Python fallback) return empty with "Invalid FHIRPath expression". End-to-end ViewDefinition yields silent NULL columns; no generate-time error. Engines DO accept plain notation at any magnitude (`0.0000001 < 0.001` → true; `1000000000000000000000.0 > 5` → true). **QA-001 MEDIUM.**
3. **NEW — decimal parse precision (probe in evolution evidence)**: `parse_view_definition` uses plain `json.loads`; `valueDecimal: 12345678901234567890.12345` parses to float `1.2345678901234567e+19` — the authored FHIR literal (FHIR decimal precision = 18 digits) is silently rounded before substitution. **QA-002 MEDIUM.**
4. Re-walked the ~90 SKEPTIC probe surface conceptually against constants.py/types.py: all 19 value[x] validations, sql-name edges, exactly-one/null/duplicate/plural rejection, lexical guards, builtin non-shadowing — unchanged, still correct. Integer64 in-range substitution unaffected by the decimal fix area.
5. Environment note: `register_fhirpath()` returned False in fresh conns (native load fails with signature error unless `allow_unsigned_extensions` config is set at connect time); fallback UDFs were used for the end-to-end probe, native probed via direct LOAD. Engines agree on all decimal behaviors, so this is a Python-side-only fix (no native dual-engine change needed).

## Found
- QA-001 MEDIUM OPEN — exponent-notation decimal substitution → invalid FHIRPath literal → silent empty results (both engines).
- QA-002 MEDIUM OPEN — json.loads float parsing silently rounds decimal constants beyond float precision.

## Verified against
SQL-on-FHIR v2 IG StructureDefinition-ViewDefinition.html (live); FHIRPath N1 grammar decimal literal (no exponent); FHIR R4 decimal precision (18 digits) and JSON representation (exponent allowed).
