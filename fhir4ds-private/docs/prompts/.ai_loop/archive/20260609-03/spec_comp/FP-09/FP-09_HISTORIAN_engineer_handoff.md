# Engineer Handoff - FP-09 HISTORIAN

Resolved issue:
- `QA-001` MEDIUM SPEC_VIOLATION.

Root cause:
- In native `Evaluator::evalFunction`, FP-09 string-search function arguments
  were evaluated with `evalArgIsolated(..., input, doc)`, where `input` was the
  already-evaluated source string collection. For sourced calls like
  `s.indexOf(term)`, the sibling path `term` was therefore evaluated against a
  primitive string and became empty.

Spec basis:
- FHIRPath §4.3 defines functions as operating on an input collection while
  arguments are FHIRPath expressions. The special per-item argument focus is
  documented for scoped expression functions such as `where`/`select`, not for
  ordinary single-value parameters such as FP-09 string search terms and bounds.
- FHIRPath §5.6.1-§5.6.5 define the concrete string-search behavior and
  singleton/type constraints.

Fix:
- `extensions/fhirpath/src/fhirpath/evaluator.cpp` now evaluates `indexOf`,
  `substring`, `startsWith`, `endsWith`, and string-function `contains`
  arguments against `outer_input` when the function has a source, otherwise
  against the current input. This preserves no-source/scoped calls such as
  `substring($this.length() - 3)` while making sourced dynamic arguments match
  the fallback.

Regression coverage:
- Added Python native/fallback parity coverage in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py`.
- Added native sqllogictest coverage in
  `extensions/fhirpath/test/sql/fhirpath.test`.
- Rebuilt and copied the bundled extension to
  `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

Validation:
- `.temp/qa/fp09_historian_probe.py`: 74 cases, 0 mismatches.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py -q`: 5 passed.
- `./build/release/test/unittest '*fhirpath*'`: 450 assertions passed.
- Full conformance via the `PROC_VALIDATION.md` filtered command:
  ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47,
  overall 2822/2822.
