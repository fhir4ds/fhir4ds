# Engineer Handoff - FP-10 EXPLORER Final

Date: 2026-06-12

## Issue Triage

| Issue | Severity | Category | Status |
|---|---:|---|---|
| QA-001 | MEDIUM | SPEC_VIOLATION | RESOLVED |
| ARCH-001 | MEDIUM | SPEC_VIOLATION | RESOLVED |
| ARCH-002 | MEDIUM | SPEC_VIOLATION | RESOLVED |

## Fix Summary

Resolved native DuckDB/C++ FP-10 regex Unicode drift for `matches()` and
`replaceMatches()`.

Root causes:
- `QA-001`: native `std::regex` treated non-ASCII character-class literals and
  negated classes as UTF-8 bytes.
- `ARCH-001`: the first class normalizer split non-ASCII literals but did not
  preserve Unicode ranges such as `[é-ë]`.
- `ARCH-002`: native `std::regex_constants::icase` did not provide Unicode
  case-insensitive behavior for non-ASCII literal/class/range patterns.

Implementation:
- Native regex normalization now has a shared UTF-8 codepoint matcher.
- Character classes are parsed into atoms/ranges.
- Positive non-ASCII class literals and mixed classes lower to grouped
  whole-codepoint alternatives.
- Negated classes lower to a negative lookahead against the class plus the
  UTF-8 codepoint matcher.
- Pure ASCII ranges stay compact; ranges with any non-ASCII endpoint expand to
  grouped whole-codepoint alternatives, skipping surrogate code points and
  preserving the normalized-regex length guard.
- When the FHIRPath `i` flag is present, non-ASCII literals, class members, and
  expanded ranges include grouped original/uppercase/lowercase variants using
  existing UTF-8 and case-mapping helpers. ASCII still uses `std::regex` icase.

## Files Changed

- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `.temp/qa/fp10_explorer_fresh_probe.py`
- `.temp/architect/golden_standard.md`
- `fhir4ds-private/docs/prompts/.ai_loop/state/deep_research_findings.md`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`
- `.ai_loop/evolution.json`, `qa_handoff.md`, `architect_handoff.md`,
  `ARCHIVE_LOG.md`, and `GLOBAL_KNOWLEDGE.md`

## Validation

```bash
python3 .temp/qa/fp10_explorer_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py -q
cmake --build extensions/fhirpath/build/release --config Release -j 8
extensions/fhirpath/build/release/test/unittest "*fhirpath*"
git diff --check -- extensions/fhirpath/src/fhirpath/evaluator.cpp extensions/fhirpath/test/sql/fhirpath.test fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension fhir4ds/fhirpath/AGENTS.md extensions/fhirpath/AGENTS.md fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp10_explorer_fresh_probe.py .temp/architect/golden_standard.md
cmp -s extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension
cmp -s extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension extensions/fhirpath/build/release/repository/v1.5.2/linux_amd64/fhirpath.duckdb_extension
python3 -m json.tool fhir4ds-private/docs/prompts/.ai_loop/evolution.json >/dev/null
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
```

Results:
- Fresh probe passed: 24 expressions.
- Focused parity passed: 4/4.
- Native unittest/sqllogictest passed: 860 assertions.
- Diff check passed.
- Extension hashes match across build, repository, and package bundle.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL
  1706/1706, DQM 47/47, overall 2822/2822.

## Notes for Architect

Audit focus should be the regex adapter boundary, especially whether the helper
is general enough without becoming an unbounded regex expander. Remaining
milestone review findings `REV-FP-002` and `REV-FP-003` are outside FP-10 and
were not changed by this remediation.
