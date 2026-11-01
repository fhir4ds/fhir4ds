# Engineer Handoff - FP-12 EXPLORER

## Issue Status

`QA-001` is `RESOLVED`.

Severity/category: `MEDIUM` / `SPEC_VIOLATION`.

## Root Cause

FHIR primitive sibling metadata was only partially preserved.

- Python fallback carried `_field` metadata on some `ResourceNode._data` member
  paths, but `children()` dropped that metadata when producing primitive child
  nodes, so root `descendants()` and primitive `children()` could not reach
  primitive extension children.
- Native C++ kept `field_name` on primitive values and had a root-level
  `_field` fallback for `extension(url)`, but nested primitives such as
  `name.given` did not know their owning `_given` metadata.

Spec basis: FHIRPath §5.8 says `children()` returns immediate child nodes and
`descendants()` is shorthand for `repeat(children())`; the primitive example
notes primitive datatype children can include extensions.

## Fix Implemented

- Python fallback:
  - `children()` now zips object fields with sibling `_field` metadata and
    carries that metadata into `ResourceNode._data`.
  - Primitive `children()` now traverses carried `_data` so extension/id
    metadata is visible from the primitive element.
  - Primitive member navigation now reads carried `_data` for paths such as
    `birthDate.extension`.
- Native C++:
  - `FPValue` now carries `primitive_shadow`.
  - `evalMemberAccess()` and `fn_children()` zip primitive values with their
    sibling `_field` metadata, including array elements.
  - `fn_extension()` and primitive `fn_children()` consume `primitive_shadow`,
    fixing nested `name.given.extension(url)` and tree traversal.
- Rebuilt and copied bundled `fhirpath.duckdb_extension`.

## Files Changed

- `fhir4ds/fhirpath/engine/invocations/navigation.py`
- `fhir4ds/fhirpath/engine/evaluators/__init__.py`
- `extensions/fhirpath/src/fhirpath/evaluator.hpp`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `.temp/qa/fp12_explorer_fresh_probe.py`
- `.ai_loop/state/deep_research_findings.md`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`

## Validation

Passed:

```bash
python3 .temp/qa/fp12_explorer_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py -q
extensions/fhirpath/build/release/test/unittest "*fhirpath*"
git diff --check -- fhir4ds/fhirpath extensions/fhirpath fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp12_explorer_fresh_probe.py
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
```

Full conformance remained 2822/2822:
ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47.

Extension hash after rebuild/copy:
`4bfa8ccf5f54457be80aa4d922670b05f3f5542e9b261fab790efa1a5eccc3a7`.

## Notes For Architect

The first native validation exposed an incomplete root `descendants()` path, so
the deep-research gate was documented in
`.ai_loop/state/deep_research_findings.md` before the second implementation
change. The final implementation fixes both direct primitive traversal and root
`descendants()` traversal through the same `children()` metadata propagation.
