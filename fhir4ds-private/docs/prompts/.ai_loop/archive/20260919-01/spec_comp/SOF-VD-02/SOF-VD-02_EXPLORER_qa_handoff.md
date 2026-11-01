# QA Handoff — SOF-VD-02 (EXPLORER), iteration 1

## Probed (PYTHONPATH=/mnt/d/fhir4ds; probes in /mnt/d/fhir4ds/.temp/qa/sofvd02_explorer/, probe1-4.py; DuckDB native extension via allow_unsigned_extensions)

Boundary probes on constants per launch mandate:
1. **%a = %b in one expression**: works (true/false both verified e2e).
2. **unionAll nested selects at depth**: constant substituted in each branch; e2e correct (Smith/Jones).
3. **%const inside forEachOrNull where-guard**: e2e correct (('phone',)).
4. **Mixed boolean where** (`gender = %Female and active`): e2e correct.
5. **Constants as function args**: `id.substring(%Start, %Len)` e2e correct. `birthDate + %Years years` REJECTED with explicit ValidationError — grammar-correct per FHIRPath N1 (quantity = Number + unit; externalConstant is a term), INTENDED.
6. **base64Binary/url/uuid/oid/canonical round-trips**: valid base64 (`PDw/Pz8+Pj0=`), url with embedded single-quote, uuid all round-trip exactly through SQL quoting. Invalid base64 rejected at parse.
7. **Builtin shadowing**: constant named `resource`/`context`/`ucum`/`rowIndex`/`rootResource` parses; `%resource` resolves to the builtin, user constant silently never usable. **QA-002 LOW** (spec-silent).
8. **120 constants** in one VD: parse + e2e arithmetic OK.
9. **sql-name edges**: leading underscore, leading digit, dash rejected (spec: "cannot start with an underscore"); single letter and 80-char names OK.
10. **Literal-only constant columns**: string/decimal/integer OK; **boolean literal column (`path: %Flag`) falsely rejected at execution as "non-primitive outputs require column.type"** — spec requires type only for non-primitive returns; Boolean is primitive. **QA-001 MEDIUM.** Root cause: `true` matches `_SIMPLE_FHIRPATH_NAV_RE` → runtime type guard whose type-unset allowed set is lowercase `_PRIMITIVE_TYPE_NAMES` only, while `type().name` returns System name `Boolean` (verified: `(true).type().name` → ['Boolean']).
11. Prior fixes re-verified e2e: exponent-edge decimals (0.00001, 1e20) both evaluate correctly; integer64-as-JSON-string in-range OK; out-of-range integer64 still raises typed ConstantResolutionError.

## Found
- QA-001 MEDIUM OPEN — bare boolean constant column falsely rejected (runtime type-guard allowed set missing System primitive names for literal `true`/`false` paths).
- QA-002 LOW OPEN — constants named after FHIRPath builtins silently unreferenceable (spec ambiguity).

## Verified against
SQL-on-FHIR v2 IG StructureDefinition-ViewDefinition.html (live, fetched this session): column.type "must be provided if a ViewDefinition returns a non-primitive type"; constant.name sql-name; value[x] substitution semantics. FHIRPath N1 grammar (quantity literal = Number + unit).

## Baseline
fhir4ds/viewdef/tests pytest: 1168 passed. conformance/scripts/run_viewdef.py: 144/144.
