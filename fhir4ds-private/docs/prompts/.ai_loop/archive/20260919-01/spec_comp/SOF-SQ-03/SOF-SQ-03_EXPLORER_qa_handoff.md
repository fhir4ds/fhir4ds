# QA Handoff — SOF-SQ-03 final launch (iteration 1, EXPLORER)

## Scope
Cross-package integration boundary conditions for `fhir4ds/sqlquery` (chunk SOF-SQ-03), on the tree as left by SKEPTIC (4 fixes) + HISTORIAN (1 docstring fix). This is the FINAL launch of the campaign; integration seam treated as last line of defense. All probes ran end-to-end against real DuckDB connections (Python-fallback and native paths).

## Probes (all in /mnt/d/fhir4ds/.temp/qa/explorer_probe1.py, explorer_probe2.py)
1. **Diamond dependency graph** (SQLQuery → sv1 + sv2, both → same VD canonical): rows correct from both consumers `[(2,2,2)]`. The shared VD canonical is resolved/materialized twice (2 resolver calls) — idempotent via `CREATE OR REPLACE VIEW`, rows correct; matches the documented statelessness. Logged EXPLORER-001 (LOW, INTENDED).
2. **Depth-5 mixed chain** (SQLQuery → SQLView → SQLQuery → SQLView → ViewDefinition): `[(2,'p1')]` correct.
3. **Main body referencing dependency view AND parameter together**: placeholder rewrite + prepared binding compose correctly `[('p1',2),('p2',2)]`.
4. **Dependency label colliding with the SOURCE table name** (`label='resources'` vs table `resources`): DuckDB Catalog error "Existing object resources …" wrapped in typed `SQLQueryMaterializationError` with label+canonical; source table NOT clobbered. Safe.
5. **Parameters through materialized dependency views**: dependency SQLView body with `:param` fails at CREATE VIEW with DuckDB Parser Error, typed `SQLQueryMaterializationError` (label+canonical). Semantics verified: parameters bind only in the main body; dependency SQLViews are static views (SQLView profile forbids parameters). Correct per spec.
6. **Unicode/emoji**: emoji + accented + guillemet string literals in SQL body execute and round-trip bytes correctly `[('p1','héllo 🩺 — «nan»')]`; unicode dependency label rejected by sql-name validation (`SQLQueryValidationError`) per ASCII-only spec invariant.
7. **Concurrent runner instances sharing one connection** (interleaved r1/r2 × 3): stable, identical rows every round.
8. **3-level nested failure**: innermost resolver failure surfaces as the top typed error carrying the INNERMOST label (`f3v`) + canonical (`urn:f3-missing`), `__cause__` chain preserved to the original KeyError.
9. **Native vs fallback parity** on the depth-5 chain: `fhir4ds.create_connection()` (native) vs plain duckdb + Python UDFs → identical rows.
10. **Parameter name identical to a dependency label**: no namespace collision; binds and executes `[(2,)]`.

## Regression sweep
- sqlquery + viewdef unit suites: **1354 passed** (sqlquery 113 + viewdef 1241).
- Master conformance gate: see engineer/architect handoff (run launched from final tree; result recorded there).
- Binary md5s (repo == site-packages): fhirpath `57d0634b6ee6eddee9fc06a1355bef5a`, cql `c5b22d58310c1eb7bafa17ce7877f989`.

## Issues
- **EXPLORER-001 (LOW, INTENDED)**: shared canonical in a diamond is materialized once per consumer edge (resolver called per edge), not deduplicated. Rows correct; `CREATE OR REPLACE VIEW` keeps it idempotent; runner docstring documents this statelessness. No action.

Zero non-terminal CRITICAL/HIGH/MEDIUM issues. Clean-exit eligible at min_iterations=1.
