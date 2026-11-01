# Engineer Handoff - FP-04 SKEPTIC

## Issue Status

- `QA-001`: `VERIFIED`

## Fix

`repeat(projection)` no longer binds a repeat-local `$index`.

FHIRPath §5.2 scoped-function semantics define `where(criteria)` and
`select(projection)` as setting `$this` and `$index`, but `repeat(projection)`
sets `$this` only and notes that `$index` is undefined/not set during repeat
iteration. The previous implementation assigned a repeat-local counter in both
backends. That made `a.repeat($index)` produce a new value for each queued item;
native C++ eventually returned empty through its infinite-loop guard, while the
forced Python fallback could hang.

Changed:
- `fhir4ds/fhirpath/engine/invocations/filtering.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `.temp/qa/fp04_skeptic_fresh_probe.py`
- FHIRPath AGENTS notes for core and native extension

Behavior now:
- Top-level `a.repeat($index)` returns empty and terminates.
- Nested `a.select($this.repeat($index))` preserves the outer select `$index`,
  returning `[0, 1]` for two input items.

## Validation

- `python3 .temp/qa/fp04_skeptic_fresh_probe.py` passed, 14 native/fallback cases.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py -q` passed, 8/8.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py -q` passed, 9/9.
- `extensions/fhirpath/build/release/test/unittest "*fhirpath*"` passed, 744 assertions.
- Full conformance summary passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Notes

The first attempted `run_all.py --help | head` invocation actually started the
suite and was cut off by the pipe, ending with `BrokenPipeError`; it was not
used as validation. The full conformance gate was rerun with the
`PROC_VALIDATION.md` grep-summary command and passed.
