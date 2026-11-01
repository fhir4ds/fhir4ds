# Engineer Handoff: CQL-11 EXPLORER

Issues resolved:
- `QA-001` HIGH: `maximum Quantity` / `minimum Quantity` now emit exact DECIMAL-backed Quantity JSON with unit/code `1`; unsupported maximum/minimum types now raise translation errors instead of lowering to SQL `NULL`.
- `QA-002` HIGH: C++-only/browser-style `predecessorOf/successorOf(VARCHAR)` now treats public numeric text as Decimal, matching Python fallback and native-loaded registration; typed Integer/Long still use numeric overloads.
- `QA-003` HIGH: Quantity literals in literal-list query sources preserve raw JSON spelling before `unnest()`, and singleton-from Quantity lists use the same raw literal path, so `from { 1 'cm' } Q return predecessor of Q` and `predecessor of singleton from { 1 'cm' }` keep integer-authored step semantics in native-loaded execution.

Files changed:
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/translator/expressions/_query.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `extensions/cql/src/cql/boundary.cpp`
- `fhir4ds/cql/duckdb/tests/integration/test_arithmetic_part2_parity.py`
- `extensions/cql/build/release/extension/cql/cql.duckdb_extension`
- `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`
- `AGENTS.md`
- `extensions/cql/AGENTS.md`
- `.temp/qa/cql11_explorer_probe.py`
- `.temp/qa/cql11_explorer_conformance_summary.log`
- `.ai_loop/state/deep_research_findings.md`

Validation:
- Fresh probe: `.temp/qa/cql11_explorer_probe.py` passed.
- Focused CQL-11 parity: `8 passed`.
- Adjacent arithmetic/macros: `74 passed`.
- Official arithmetic parser subset: `348 passed`.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

Recovery note:
- A broad Quantity-literal translation change initially fixed part of `QA-003` but regressed full conformance to CQL 1666/1706 and DQM 45/47. It was reverted before the targeted query-source and singleton-from preservation fix. Details are in `.ai_loop/state/deep_research_findings.md`.
