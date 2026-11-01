# Engineer Handoff — CQL-21 FIX (iteration 1), QA-001 age uncertainty

## Fixture adjudication (the CRITICAL pre-fix step)
The CQL conformance gate (1706 tests) runs the 16 XML files in
`fhir4ds/cql/tests/official/cql-tests/tests/cql/` — there is **no
CqlAgeOperatorsTest.xml** anywhere in the repo or the suite, so **no official
fixture pins crisp partial-birthDate age behavior**. The QA handoff's
"official XML suite has NO age tests (requires patient context)" was
re-confirmed. The CQL-13 EXPLORER follow-up note ("CalculateAge* UDFs keep
the crisp day-1 partial-birthDate convention") was chunk-ownership deferral,
not a fixture pin. Spec prose therefore governs → **implement uncertainty**.

## What was fixed (QA-001 RESOLVED)
The interrupted prior session had implemented most of the fix in the working
tree; this session verified it end-to-end, completed it, and repaired two
gaps:
1. **Verified implemented**: Python `udf/age.py` delegates every age surface
   to `_duration_between_with_uncertainty` (§22.21 VARCHAR
   scalar-or-interval; crisp negative → null; intervals surfaced); native
   `age.cpp`/`cql_extension.cpp` `AgeFromStringTexts` =
   `AgeTextGuarded(CqlDurationBetweenString(...))`; translator bare
   `AgeIn*()` → `cqlDurationBetween` with Today()/Now() per §Age; one-arg
   `AgeIn*At(asOf)` → `CalculateAgeIn*At`; age family added to
   `_UNCERTAIN_BETWEEN_UDFS` so comparisons route through
   `cqlUncertainCompare`.
2. **Rebuilt + deployed the native extension** — the tree's binary
   (19:56) predated the last cql_extension.cpp edit (19:58); rebuilt
   (cmake --build build/release), deployed to repo bundle + site-packages,
   `~/.duckdb/extensions` cache cleared. md5
   `82b234168290f6a6053b583d70e3d9d6` matched across
   build/bundle/site-packages. This alone fixed 2 parity failures
   (native AgeInHoursAt returning NULL instead of interval JSON).
3. **Fixed DQM regression found at the Recovery Gate**: 11 measures
   (CMS2/74/75/122/124/125/130/155/165/334/349) failed with
   `Binder Error: Cannot mix VARCHAR and INTEGER_LITERAL in BETWEEN` —
   `age in Interval[a, b]` lowered to a raw SQL BETWEEN over the now-VARCHAR
   age. Root-cause fix in `_operators.py` interval-`in` lowering: when the
   operand is uncertainty-capable (`_is_uncertain_between_expr` /
   `_uncertain_between_sql`), lower to `cqlUncertainCompare(x,a,'>=') AND
   cqlUncertainCompare(x,b,'<=')` per CQL `in` ≡ (x >= a and x <= b).
4. **New regression test**
   `test_cql_clinical_age_partial_birthdate_uncertainty_matches_cpp_registration`
   (direct UDF + cqlUncertainCompare three-valued semantics + Patient-context
   population SQL with birthDate '1990' → {"start":35,"end":36}, on py+cpp).
   Note: population-mode boolean defines are filter-based, so an uncertain
   comparison surfaces as False at the define boundary (NULL collapses to
   row-exclusion); the scalar NULL-vs-false distinction is asserted via the
   direct cqlUncertainCompare cases.

## Files changed (this session)
- `fhir4ds/cql/translator/expressions/_operators.py` (interval-`in`
  uncertain-conjunction lowering)
- `fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py`
  (new QA-001 regression test)
- rebuilt `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`
  (md5 82b234168290f6a6053b583d70e3d9d6; repo bundle == site-packages ==
  build output; ~/.duckdb cache cleared)
(Prior interrupted session's fix files retained: udf/age.py, udf/datetime.py,
extensions/cql/src/cql/age.{cpp,hpp}, cql_extension.cpp, translator
_functions.py/_operators.py age wiring, test_age_udfs.py, parity pins.)

## Validation
- Focused: test_age_udfs + test_clinical_operator_parity +
  test_datetime_udfs + test_arrow_udfs → 124+ passed; clinical parity suite
  51/51 after final edits.
- Master gate (fresh, final tree): see GLOBAL_KNOWLEDGE stats row —
  2832/2832 restored (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).

## Out-of-chunk discovery (QA-002, MEDIUM, DEFERRED)
Full CQL unit-suite run at the Recovery Gate found
`test_logical_parity.py::test_cql_boolean_define_alias_feeds_logic_by_value`
failing: `define F: Patient.active; define G: F and true` →
TranslationError "requires Boolean operands; got List<Any>". Bisect vs
committed HEAD (db1e4164, translates fine) proves it is pre-existing in the
shared campaign tree (CQL-19-era `_definition_is_dynamic_list` fhirpath_text
shape-marking colliding with the CQL-04-era `_validate_boolean_operand`
guard on stored-list aliases of single-valued Boolean properties). NOT on
the CQL-21 fix path. Deferred to the list/property-typing chunk owner;
suggested fix: gate dynamic-list marking on FHIR max-cardinality > 1.
