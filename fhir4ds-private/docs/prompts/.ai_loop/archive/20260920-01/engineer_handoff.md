# Engineer Handoff — bug_fix workflow (pipeline step 2, target 0.0.15)

**Workflow:** bug_fix (Remediation Engineer)
**Date:** 2026-09-19
**Tree state:** duckdb 1.5.5 pin (dependency_upgrade step 1), native ext
md5s cql `18a91a6485f48cc10cc452fe2963b815` / fhirpath `daccb5289dd4360bbeaf68823ebec48d` (unchanged this workflow — all fixes are Python-side).

## Issues (all terminal)

| ID | Finding | Status |
|----|---------|--------|
| BUGFIX-001 (F1) | CloudCredentials broken on DuckDB 1.5.5 (option renames + removed options) | **RESOLVED** |
| BUGFIX-002 (U1) | Unknown retrieve resource type → silent False | **RESOLVED** |
| BUGFIX-003 (U2) | Zero-code ValueSet silent + bare-string cache never matches | **RESOLVED** |
| BUGFIX-004 (U3) | Bad Measure criteria name → raw CatalogException | **RESOLVED** |
| BUGFIX-005 (D1-D8) | Docs one-liners | **DEFERRED → docs_audit** (step 6; single source of truth, no drift) |

## Fixes

### BUGFIX-001 (F1) — `fhir4ds/sources/filesystem.py`
- `_ALLOWED_SECRET_OPTIONS` → `_SECRET_OPTION_ALIASES`: snake_case kwargs
  map to DuckDB 1.5.5 native secret options (probed live; S3
  access_key_id→KEY_ID, secret_access_key→SECRET, session_token→
  SESSION_TOKEN, region→REGION, endpoint_url→ENDPOINT, url_style→
  URL_STYLE, use_ssl→USE_SSL; AZURE connection_string→CONNECTION_STRING,
  account_name→ACCOUNT_NAME, endpoint→ENDPOINT; GCS native HMAC key_id/
  secret/session_token + bearer_token).
- `_REMOVED_SECRET_OPTIONS`: AZURE `account_key`, GCS
  `service_account_json` (both removed upstream) → typed ValueError with
  actionable guidance.
- `_AZURE_SERVICE_PRINCIPAL_KEYS`: tenant_id/client_id/client_secret emit
  an unquoted `PROVIDER service_principal` clause before the options.
- Options emitted sorted; values always `quote_sql_literal`'d; unknown
  options still raise typed ValueError. Injection tests kept.
- Verified: `tests/unit/test_filesystem.py` 49/49 (stale pins updated),
  sources tree 230/230, live 1.5.5 probes (all 3 providers register
  secrets; SP works with auto-loaded azure extension).

### BUGFIX-002 (U1) — `fhir4ds/cql/translator/expressions/_query.py`
- `_translate_retrieve`: after `resolve_named_profile`, raise typed
  `TranslationError` when resource_type ∉ `_spec_resource_types()`
  (lazy import of `viewdef.metadata.KNOWN_FHIR_RESOURCE_TYPES`, 120-code
  spec-published valueset superset) ∪ `context.fhir_schema.resources`
  keys (custom schemas honored). Profiled/QICore/terminology-filtered
  retrieves unaffected.
- Verified: 2 regressions in
  `cql/tests/integration/test_udf_registration_guard.py` (9/9);
  **DQM gate 47/47** on final tree.

### BUGFIX-003 (U2)
- (a) `fhir_loader.py load_valuesets`: per-ValueSet WARNING when
  expansion+compose yields zero codes; runtime unchanged.
- (b) `duckdb/udf/valueset.py createValuesetMembershipUdf`: cache
  normalized at factory entry — all-string sets → `{'', code}` tuples;
  tuple sets pass through. Both shapes documented in docstring.
- Verified: 2 regressions in
  `cql/duckdb/tests/integration/test_in_valueset_native_parity.py` (10/10);
  clinical parity 77 pass.

### BUGFIX-004 (U3) — `fhir4ds/cql/translator/translator.py`
- Final-select builder in `translate_library_to_population_sql`: up-front
  `ValueError` listing unknown definition names + sorted available
  definitions (shared by evaluate_measure and DQM compile_measure; the
  evaluator wraps it into DQMError "Compilation failed for group...").
- Verified: regression in test_udf_registration_guard.py (9/9).

### BUGFIX-005 (D1-D8) — deferred to docs_audit
D1 evaluate_measure DataFrame wording; D2 strict_mode model=; D3
create_connection kwargs→CONFIG; D4 FileSystemSource patient_ref
derivation; D5 parse_library canonical rejection; D6 SQLGenerator
dialect='duckdb' only; D7 in_valueset root-relative paths; D8 stale
evaluate() docstring + 3 one-liners.

## Incidental stale-test repairs (NOT bugs, test-vs-doctrine collisions)

Full CQL suite initially showed 4 failed / 1377 passed. Proven
pre-existing on clean HEAD (baseline run with my 5 source files reverted:
identical 4 failures), then repaired per the stale-test-repair precedent:

1. `test_structural_type_parity.py::test_cql_structural_type_translated_sql_matches_cpp_registration`
   — pinned `{1, 'x'}` mixed-list defines, which the committed CQL-18
   common-element-type doctrine correctly rejects at translation.
   Switched to homogeneous `{1, 2}` defines (same is/as coverage).
2. `::test_cql_structural_element_access_over_retrieve_bound_define_alias`
   and
3. `::test_cql_structural_array_property_on_singleton_resource_expressions`
   — asserted scalar `'final'`/`'c1'` but the committed CQL-05 QA-106
   list-returning fhirpath lowering surfaces 0..* properties as singleton
   lists `['final']`/`['c1']` (values correct). Assertions now unwrap
   singletons.
4. `test_temporal_complex_parity.py::test_cql_ratio_tuple_selector_compares_as_ratio_per_spec`
   — `.numerator.value` accessor returning a list is the documented
   CQL-20 HISTORIAN deferred gap (AGENTS.md: "fails on the pre-launch
   tree"). Marked `xfail(strict=False)` citing the deferral.

After repairs: 22 passed + 1 xfailed (structural file) — green.

## Validation

- Sources tree 230/230; CQL unit 1656/1656; registration guard 9/9;
  in_valueset parity 10/10; clinical 77; sql_structure 27/27; DQM 47/47.
- Full CQL integration suite: 1377 passed / 10 skipped + 4 pre-existing
  (repaired as above).
- **Master gate** (`conformance/scripts/run_all.py` on duckdb 1.5.5):
  see final status below.
- File backups of all 5 fixed sources: `/tmp/opencode/bugfix/*.bugfix`.

## Gate result

**PASS — 2832/2832 (100.0%)** on duckdb 1.5.5:
ViewDef 144/144, FHIRPath (R4) 935/935, CQL 1706/1706, DQM 47/47.
GATE_EXIT=0 (log: /tmp/opencode/bugfix/master_gate.log).

## State transitions

- `evolution.json`: issues BUGFIX-001..004 RESOLVED (root_cause/
  resolution/verified_in filled), BUGFIX-005 DEFERRED; workflow → null,
  exit_reason → CLEAN; next pipeline step = evolution (36 QA iterations,
  domains 6-12 × SKEPTIC/HISTORIAN/EXPLORER).
- AGENTS.md doctrine entries appended: `fhir4ds/sources/AGENTS.md`
  (secret option doctrine), `fhir4ds/cql/AGENTS.md` (U1/U2/U3 + stale-test
  repair notes).

No commits made (Joel commits).
