# QA Handoff — SOF-VD-07 EXPLORER (iteration 1)

Personality: EXPLORER (boundary probing). All probes ran against DuckDB with
Python-fallback FHIRPath (native extension not loadable in this env; verified
`_is_cpp_extension_loaded()==False`).

## Probes executed (.temp/qa/probe.py)
- P1 repeat with 12 union paths: PASS (12 distinct nodes, correct depth-first union).
- P2 wide tree 1000 siblings at depth 2: PASS (2000 rows, depth-first interleaving, 1.1s).
- P3 deep chains 3000/6000: correctness PASS (3001/6001 rows) but 43.5s/178.5s — QA-002 (LOW, perf).
- P4 repeat→forEach→repeat 3 alternating levels: PASS (1 row 'c', correct).
- P5 nested extension-of-extension repeat: PASS for url-bearing wrappers.
- P6 contained ofType(Observation) inside repeat: PASS (o1, o2 collected recursively).
- P7 collection=true column under repeat: PASS (per-node multi-values ['1','2'], ['3']).
- P8 %rowIndex under repeat: rows 0..n-1 — PASS but row set truncated by QA-001.
- P8b %rowIndex inside forEach under repeat: 0 rows — WRONG (QA-001 collateral).
- P9 repeat branch inside unionAll: PASS.
- P10 subtree-isomorphism dedup: PASS (identical subtree at different depths collapsed; 3 rows matches union-dedup reference math: same, same2, None).
- P11 SQL shape: flattened CROSS JOIN LATERAL + fhirpath_repeat UDF, no recursive CTEs — expected.
- P12 repeat where-expression path: PASS (0 rows correct: root-level filter excludes all).
- 3D arrays-of-arrays under repeat: [] (lists filtered, only dict nodes traversed) — acceptable, FHIR never produces this.

## QA-001 (HIGH, OPEN): extension-only elements silently dropped by FHIRPath layer
`fhirpath.evaluate(res, 'extension'|'x')` drops any element whose ONLY key is
`extension`, e.g. `{"extension":[{"url":"c"}]}`. Valid FHIR (backbone elements /
nested Extensions with only extension content). Breaks SOF-VD-07 repeat row
counts: repeat['extension'] on [a, b, wrapper{extension:[c]}] emits 2 rows,
expected 4 (a, b, wrapper, c). Also zeroed repeat→forEach stacks.
Root cause: top-level post-filter in `fhir4ds/fhirpath/__init__.py`
`apply_parsed_path` drops ANY ResourceNode with data.keys()==['extension'];
intended only for `_field`-synthesized primitive-extension shadow nodes.
Native C++ evaluator has no such filter (no drop logic found), so the Python
fallback is the divergent engine. Official repeat.json fixtures do not cover
extension-only elements, so 144/144 passes despite the bug.

## QA-002 (LOW): deep-tree repeat is O(n^2)
43.5s @ depth 3000, 178.5s @ depth 6000. Inherent to per-node subtree
serialization for value-dedup. Observation only; recommend no fix this launch.

## Environment note
Official test harness's regex table substitution (`FROM x t` → `... WHERE ...`)
breaks SQL when JOINs follow FROM; probes used a derived-table substitution.
