# Architect Handoff — SOF-VD-06 (forEach/forEachOrNull), HISTORIAN iter 1

## Scope
Structural audit of the forEach family in fhir4ds/viewdef (parser.py iterator-combo validation, unnest.py lateral generation, generator.py wiring) against the chunk mandate.

## Golden-standard invariants checked (chunk-scoped)
1. Iterator combo policy centralized in parser (forEach/forEachOrNull/repeat mutual exclusion at parse AND re-validation walk) — holds; error message shared.
2. Built-in variable set canonicalized in constants.py:FHIRPATH_BUILTIN_VARIABLES — holds; no duplication in generator; %parent correctly not a builtin.
3. unnest.py owns all lateral SQL; generator does not hand-build unnest fragments — holds; null-preserving UNION ALL pattern documented in-code against Process(S,N) step 3.
4. No silent fallbacks: undefined constants and duplicate column names fail fast — holds.
5. No fixture-specific hacks in iterator paths — none found.
6. fhirpath/fhirpath_json UDF pairing used by unnest stays length-aligned — verified empirically.

## QA quality gate
QA (HISTORIAN) covered the full chunk item list with new probes beyond the SKEPTIC pass (column+forEach canonical form, union-under-forEach, forEach-in-unionAll canonical spec example, constants rejection, mixed collections, empty JSON arrays, key typing, %parent rejection, UDF alignment). Initial bug suspicions were rigorously bisected and all traced to harness artifacts, not product bugs. Sufficient — no veto, RETRY_QA=false.

## Findings
0 CRITICAL / 0 HIGH / 0 MEDIUM. 2 LOW INTENDED observations (QA-001 forEach+unionAll same select, spec-silent; QA-002 no normative row order). Recommended fix order: none.

## Compression
QA and Engineer phases confirm the forEach family is Process(S,N)-conformant with no remaining actionable divergence; engineer made no changes; gates fresh and green.

## Gates (final tree)
run_all.py 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47); viewdef pytest 1185 passed; fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a identical across repo bundle and site-packages (no rebuild needed).

## Verdict
Clean exit at min_iterations=1.
