# QA Handoff — CQL-20 Aggregate Functions (SKEPTIC, iteration 1)

Spec source verified: CQL 1.5 Appendix B "Aggregate Functions" (fetched from HL7/cql
`input/pages/09-b-cqlreference.md`; cached at /tmp/cqlref.md lines 5470–5882).

## What was probed
1. **Probe 1** (`.temp/qa/cql20agg_skeptic_probe1.py`) — empty-list → null, all-null lists,
   null operand, single-element sample/population stats, median even-count, overflow (Integer
   and Long Sum → null), exact-decimal Sum/Avg, GeometricMean incl. zero/negative, py==cpp
   across 32 literal/query-literal defines. **All conformant** on this surface. GeometricMean of
   negatives → null (matches reference-engine ln() convention; spec formula is ambiguous) —
   adjudicated INTENDED.
2. **Probe 3** (`.temp/qa/cql20agg_skeptic_probe3.py`) — end-to-end population SQL
   (translate_library_to_population_sql) over a 2-patient FHIR fixture, py/cpp/no-python
   parity, 28 aggregate cases over: dynamic multi-valued fields (Patient.name.given),
   query-derived Quantity lists (`(from [Observation] O return O.value as Quantity)`),
   query-derived dateTime lists, retrieves, filtered queries, unions, alias defines.

## Findings (6 issues, logged in evolution.json)
- **QA-001 HIGH** — Min/Max/Median over query-derived Quantity define aggregates only the
  FIRST row (`LEAST((SELECT ... LIMIT 1))`); Min({120,80}mg) returned 120. Silent wrong values.
- **QA-002 HIGH** — Sum/Avg/PopulationStdDev/PopulationVariance over the same Quantity define
  → BinderException GROUP BY; Median/StdDev/Variance/Product → Binder lambda-binding error.
  Spec defines Quantity overloads for all.
- **QA-003 HIGH** — Min/Max/... reject `List<dateTime>`: FHIR choice-cast `as dateTime` type
  name is not normalized to CQL `DateTime`, so spec-supported DateTime overloads are refused.
- **QA-004 HIGH** — AllTrue/AnyTrue over retrieve-backed query sources emit a broken
  correlation (`WHERE O.patient_id = _agg.patient_id` inside the _agg subquery, no GROUP BY)
  → BinderException.
- **QA-005 MEDIUM** — Mode over dynamic multi-valued field: scalar MODE() over JSON list,
  UNNEST-correlated binder error.
- **QA-006 MEDIUM** — Product(List<Integer>) returns Decimal 24.00000000 (spec: Integer);
  Product lacks the CQL-01 exact/typed treatment Sum received.

## Confirmed-conformant surfaces (no action)
Empty→null for all non-Count aggregates; Count(null-list)=0; AllTrue(null)=true /
AnyTrue(null)=false; null-element ignoring; single-element StdDev/Variance → null and
PopulationVariance → 0; Sum overflow → null (Integer and Long); Sum({0.1,0.2})=0.3 exact;
Avg exact via cqlDivide; Median even count → 5.0; Mode tie → null; Count over dynamic
fields/aliases/retrieves/unions/filtered queries; Min/Max over String/Date/Time/DateTime
literal lists and dynamic String fields; GeometricMean zero → 0.0, empty → null.

## Root-cause pointers for Remediation
- The `_translate_aggregate_pre` Identifier branch (`_functions.py` ~2100–2140) handles
  `stores_list_value` defines for count/min/max/sum/avg via `list_*` functions and
  `List<Quantity>` only when the define AST translates to a Quantity SQLArray — a
  query-derived define falls through to the generic `_wrap_list_aggregate`/
  scalar-subquery paths that produce LIMIT-1 / GROUP BY / _agg-correlation shapes.
- `_validate_static_aggregate_argument` allowlist lacks FHIR→CQL type-name normalization
  (`dateTime`→`DateTime`).
- Mode never routes dynamic operands through `CQLListMode`.
