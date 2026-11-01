# QA Handoff - FP-09 HISTORIAN

## Scope

- Iteration: 1
- Personality: HISTORIAN
- Chunk: FP-09
- Spec focus: FHIRPath continuous-build §5.6.1-§5.6.5 String Manipulation
  search functions: `indexOf(substring)`, `substring(start[, length])`,
  `startsWith(prefix)`, `endsWith(suffix)`, and string-function
  `contains(substring)`.
- Spec source consulted:
  `https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md`

## Normative Baseline

- These string functions operate on a singleton String input; multi-item input
  or non-String input is an evaluation error.
- Singleton arguments must have the declared type: String for search terms and
  Integer for `substring` bounds.
- Empty input or empty required argument collections produce empty results.
- Empty String search terms return `0` for `indexOf` and `true` for
  `startsWith`, `endsWith`, and string-function `contains`.
- `substring` positions and lengths are measured in Unicode scalar values.
  Start positions outside or equal to the string length return empty; zero or
  negative length returns the empty String.
- `.contains()` is the string substring function and is distinct from the
  collection `contains` operator.

## Fresh Probe

Created and ran `.temp/qa/fp09_historian_fresh_probe.py` from scratch for this
launch. The probe opens both a native DuckDB/C++ FHIRPath registration and a
forced Python fallback registration, then compares every public UDF output
between them.

Coverage included:

- Normative examples and boundary behavior for all five functions.
- Empty String search terms and empty input/argument collections.
- Unicode scalar indexing for emoji/surrogate-pair characters and combining
  marks.
- Dynamic sibling-field arguments at root and inside `select()` scoped focus.
- Runtime non-String and multi-item input/argument row resilience.
- Static malformed argument types and arities via `fhirpath_is_valid()`.
- String `.contains()` versus collection `contains` operator disambiguation.

## Findings

No issues were opened. Native DuckDB/C++ and forced Python fallback matched on
the fresh 66-expression probe, and pinned outputs matched the current FHIRPath
§5.6.1-§5.6.5 requirements for the spec-relevant result columns.

Milestone review findings `REV-FP-002` and `REV-FP-003` were noted but did not
intersect this chunk's string-search behavior. They remain outside this pass.

## Validation

- `python3 .temp/qa/fp09_historian_fresh_probe.py`

## Handoff

Proceed to FIX as a no-op remediation pass: there are no `OPEN` or
`CONFIRMED` FP-09 HISTORIAN issues in `evolution.json`.
