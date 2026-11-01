# QA Handoff — SOF-VD-10 HISTORIAN (2026-08-23)

Chunk: SQL-on-FHIR v2 ViewDefinition cross-cutting validation (sql-name /
sql-expressions invariants, required fields, bindings, expectError handling,
mode separation). HISTORIAN pass on the tree left by the SKEPTIC launch
(zero fixes there; 95-assertion sweep clean).

## Spec verified against
- v2 SD 2.0.0 (cached `.temp/qa/sof_vd10_skeptic_2026_08_23/sd-vd-v2.json`):
  full element + invariant dump. Confirmed: sql-name on ViewDefinition.name /
  constant.name / column.name only; sql-expressions on select; root where
  0..*; NO select.where / select.repeat element in the SD snapshot (both are
  reference-validator + established-doctrine additions).
- Official validator fetched fresh:
  `FHIR/sql-on-fhir.js@main/sof-js/src/validate.js` (4745 bytes). Key facts:
  top-level additionalProperties:false but properties limited to
  id/title/status/description/resourceType/name/url/version/resource/
  constant/select/where (no meta/profile/fhirVersion — SD outranks it there,
  per existing SOF-VD-01/G-3 doctrine). Constant items have NO
  additionalProperties:false; value[x] is a oneOf over 20 typed fields.
  Tag items {name,value} strings, additionalProperties:false, no required.
  Column minItems:1, select minItems:1, repeat minItems:1.

## Probes (workspace `.temp/qa/sof_vd10_historian_2026_08_23/`)
1. Validation-order interactions: bad name + missing resource → resource
   error surfaces; bad name + missing select → select error; deeply
   malformed (bad name + 3-way iterator combo + missing column.path) →
   single typed ParseError (column.path), no stack trace; unknown resource +
   bad const name + dup column → single typed ParseError. All 20 assertions
   typed ParseError (only probe-authoring bug: wrong resourceType URL).
2. Malformed-shape sweep: list/scalar/empty-object roots, select=dict,
   select item=string, column=null, constant=string, where non-array /
   missing path, name=null — all typed rejections; int input raises
   TypeError (documented parse_view_definition contract).
3. Constants oneOf semantics vs official validator: dual value[x],
   missing value[x], null value[x], valueInteger=1.5, valuePositiveInt=0,
   valueUnsignedInt=-1 all rejected; unknown constant fields ACCEPTED
   (matches official — constant items lack additionalProperties:false).
4. Tags: unknown tag field / missing value / non-string value / null name
   all rejected (official additionalProperties:false honored).
5. Maximal valid VD strict round-trip: every optional field (id/url/version/
   name/status/title/description/profile/fhirVersion/meta/publisher-as-
   extra/4 typed constants/tag/collection/type/forEach+forEachOrNull+unionAll/
   nested where/root where) parses, to_dict→from_dict→to_dict stable,
   extra_fields preserved, meta round-trips.
6. 3.0.0-ballot SD coverage (informational): ballot-only fields
   (`encoding`, `autoName`) accepted and preserved verbatim in extra_fields —
   newer invariants are NOT enforced (2.0.0 scope respected).
7. Dual-engine DuckDB execution of a decimal-constant VD
   (`%factor * 3` with valueDecimal 2.5): SQL generation + execution OK.
8. Error-message consistency: all sampled fault messages name the offending
   field and cite the violated invariant.

## Findings
- 0 CRITICAL / 0 HIGH / 0 MEDIUM.
- QA-001 LOW DEFERRED: `Constant.to_dict()` emits `decimal.Decimal` for
  `valueDecimal` on the strict JSON-string parse path, so
  `json.dumps(vd.to_dict())` raises TypeError; also dict-input vs
  string-input parses yield float vs Decimal (dataclass inequality across
  entry points). No production consumer; loud failure, no silent corruption;
  stdlib json cannot losslessly encode arbitrary-precision decimals.
- QA-002 LOW INTENDED: `valueInteger: 3.0` (JSON number with decimal point)
  is rejected ("must be a JSON integer"). Ajv `integer` accepts 3.0
  (JS Number.isInteger), but FHIR integer representation forbids a decimal
  point; stricter typed boundary is defensible.
- QA-003 LOW INFO/INTENDED: select-level `where` and `repeat` accepted per
  doctrine (reference validator / SOF-VD-05/09), though absent from the
  2.0.0 SD snapshot — re-confirmed, no change.
