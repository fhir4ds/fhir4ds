# QA Handoff — SOF-VD-06 (select.forEach / forEachOrNull), EXPLORER iter 1

## Approach
Chaos/boundary probing per EXPLORER mandate, on ground not covered by SKEPTIC/HISTORIAN launches.
Harness: /mnt/d/fhir4ds/.temp/qa/sof_vd06_explorer/ (harness.py reused; p1 heavy-FHIRPath+exotic-collections, p2 rowIndex/constant/depth-5, p3 forced-Python-fallback parity, p4 chaos edges). All runs end-to-end DuckDB execution of generated SQL.

## Probed (new ground vs prior launches) — ALL CONFORMANT
- Heavy FHIRPath in forEach targets: exists()-gated iteration (name.where(family.exists())), where().first() iteration targets, iif()-driven targets (iif(active, name.family, name.given) → correct branch), deep chains. Note: multi-item input to singleton string fn (name.given.substring(0,3)) errors → treated as empty (FHIRPath singleton doctrine, engine-side, not viewdef).
- Exotic collections: filtered extension arrays (url=...), contained.ofType(Observation) fast-path iteration (native + fallback), heterogeneous contained iteration with resourceType column, BackboneElement chains at depth (identifier.type.coding, per-level %rowIndex), collections-of-collections via collection=true under forEach, count()/boolean singleton foci.
- Null-valued array elements [a, null, b]: FHIRPath excludes JSON nulls from collections → 2 foci, %rowIndex 0,1 over the filtered collection (p2.4/p2.5, forEach and forEachOrNull; mixed-null multi-valued same result). Consistent with FHIRPath §collection semantics; no row yielded for the null element in either engine.
- forEach expression evaluation ERROR (type error in where) vs empty: uniform tolerant-empty treatment — forEach 0 rows, forEachOrNull 1 null-preserved row (QA-001 INTENDED; Process(S,N) defines no error semantics; native==fallback).
- %constant lists under forEach: not expressible per SD (value[x] primitive singletons) — ParseError correct (QA-002 INTENDED).
- %rowIndex in deeply nested iteration feeding arithmetic (%rowIndex + 10) and where clauses (%rowIndex < 1, %rowIndex + 1 = 2 at depth 3): correct, 0-based, per-level reset.
- Depth-5 iteration (nested extension): correct row, 5 JOIN LATERALs, deterministic SQL (2350 chars) — sane shape.
- %context under depth-2 iteration ($this = %context true per focus), %rootResource.id correct from depth.
- Scalar singleton focus (gender) + nested forEachOrNull on absent child → null-preserved row; per-focus where under forEachOrNull (only matching foci survive).

## Issues
Zero CRITICAL/HIGH/MEDIUM. Two LOW spec observations (QA-001, QA-002) logged INTENDED.

## Gates
- pytest fhir4ds/viewdef/tests: 1185 passed.
- run_viewdef.py: 144/144 (100%).
- Master gate run_all.py: running; result in engineer/architect handoff.
- Binary md5: fhirpath.duckdb_extension 57d0634b6ee6eddee9fc06a1355bef5a — repo == site-packages.

## Verdict
Clean-exit eligible at min_iterations=1. No code changes required.
