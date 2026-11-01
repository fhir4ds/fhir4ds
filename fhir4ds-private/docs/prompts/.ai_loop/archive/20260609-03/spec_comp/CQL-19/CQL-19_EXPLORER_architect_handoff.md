# Architect Handoff - CQL-19 EXPLORER

Golden standard written to `.temp/architect/golden_standard.md`.

Audit result:
- No new structural findings.
- The final fix is scoped to scalar CQL list-query boundaries and does not collapse retrieve/resource-backed query rows. This preserves DQM patient correlation while allowing list operators to receive true `List<T>` values for scalar query expressions.
- The helper is AST-based and uses SQL AST nodes rather than SQL string rewriting.
- QA was sufficient; no `RETRY_QA` flag is needed.

Issue status:
- `QA-001` verified and archived. Query-produced scalar lists now work with `Last`, `Length`, `Tail`, `Skip`, `Take`, proper inclusion, list union, and `singleton from` across forced Python fallback, native-loaded registration, and no-Python/browser-style C++.

Validation:
- `.temp/qa/cql19_explorer_probe.py`: passed.
- `test_list_part1_parity.py` + `test_list_part2_parity.py`: 17/17 passed.
- Official `CqlListOperatorsTest`: 424/424 passed.
- Full conformance: 2822/2822.
