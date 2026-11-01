# QA Handoff — SPEC FP-05 EXPLORER

## Scope
- Workflow: `evolution`
- Phase completed: `QA`
- Iteration: `1`
- Personality: `EXPLORER`
- Spec chunk: FHIRPath §5.3 Subsetting and §5.4 Combining
- Spec source: official HL7 FHIRPath continuous-build source, `input/pages/index.md`

## Normative Expectations Checked
- `[index]` is 0-based; empty input, empty index expression, and out-of-range indexes return empty.
- `single()` returns the sole item, returns empty for empty input, and signals an evaluation error for multi-item input.
- `first()`, `last()`, `tail()`, `skip(num)`, and `take(num)` preserve the §5.3 empty, boundary, and non-positive-count behavior.
- `intersect()` and `union()` eliminate duplicates using FHIRPath `=` equality.
- `exclude()` preserves duplicates/order for retained input items.
- `combine(other)` preserves duplicates, and `combine(other, true)` appends the other collection while preserving both collection orders.

## Fresh Exploration
- Created `.temp/qa/fp05_explorer_fresh_probe.py` for this launch.
- Ran 43 fresh expressions against both the bundled native DuckDB/C++ extension and the forced Python fallback.
- Probed dynamic scoped argument cases such as `groups.select(left[n])`, `groups.select(left.skip(n))`, `groups.select(left.take(n))`, and `groups.select(left.combine(right, flag))`.
- Probed invalid index/count/preserveOrder shapes, duplicate-retaining `combine()`/`exclude()`, duplicate-removing `union()`/`intersect()`, empty collection boundaries, and resource-backed `value[x]` paths.

## Findings
- No issues opened.
- Native DuckDB/C++ and forced Python fallback matched on the fresh FP-05 probe.
- Focused parity tests and full conformance remained green.

## Validation
- `python3 .temp/qa/fp05_explorer_fresh_probe.py` passed, 43 expressions.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py -q` passed, 11/11.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py -q` passed, 9/9.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM" > .temp/qa/fp05_explorer_conformance_summary.log && cat .temp/qa/fp05_explorer_conformance_summary.log` passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
