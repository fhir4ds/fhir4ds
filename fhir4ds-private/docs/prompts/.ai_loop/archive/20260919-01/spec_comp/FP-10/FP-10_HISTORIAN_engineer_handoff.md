# Engineer Handoff — FP-10 HISTORIAN (iteration 1)

QA-001 (HIGH) and QA-002 (MEDIUM) RESOLVED; QA-003 (LOW) DEFERRED with
pinned dialect divergences. Triage: QA-001 SPEC_VIOLATION, QA-002
API_CONTRACT, QA-003 DIALECT.

## QA-001 — native named capture groups + ${name} substitution

Root cause: std::regex ECMAScript has no `(?<name>…)` syntax and
std::regex_replace has no `${name}` form, so the §5.6.10 canonical
replaceMatches example was unrunnable on the native path (is_valid=False,
empty). Python-side siblings of the same root: the engine `matches()`
(strings.py) compiled the raw pattern (only replace_matches translated
named groups), and `fhirpath_is_valid`'s regex-literal precheck
(`udf.py::_has_invalid_string_regex_literals`) also compiled raw, so the
fallback reported is_valid=False for valid §5.6.10 syntax.

Changes:
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`:
  - `isRegexNamedGroup()` + translation inside `normalizeFHIRPathRegex`:
    `(?<name>…)` becomes a plain capturing group (order/numbering
    preserved; lookbehind `(?<=`/`(?<!` deliberately left on the invalid
    path). Bug caught during verification: the initial emptiness guard
    rejected single-char names (`(?<n>a)`) — fixed.
  - `fhirpathNamedGroupNumbers()` (counts capturing groups, skipping
    escapes, char classes, leading inline flag groups, non-capturing
    groups) + `translateNamedGroupSubstitution()` (rewrites `${name}`
    for EXISTING named groups to `$N`; `$N`/`$$`/`$word`/`${unknown}`/
    `${N}` pass through so documented literal/empty behaviors stay
    byte-identical across engines), applied once at the fn_replaceMatches
    site before both the multiline line-wise and normal paths.
- `fhir4ds/fhirpath/engine/invocations/strings.py`: new shared
  `_translate_named_groups()`; `matches()` now uses it (replace_matches
  refactored onto the same helper).
- `fhir4ds/fhirpath/duckdb/functions/string.py`: direct helper `matches()`
  applies `_translate_named_groups` (FP-09 helper doctrine).
- `fhir4ds/fhirpath/duckdb/udf.py`: `_has_invalid_string_regex_literals`
  compiles through `_translate_named_groups` (message-coupled classifier
  lockstep).
- Extension rebuilt (`cmake --build . --target fhirpath_loadable_extension`)
  and redeployed to repo bundle, user site-packages, and ~/.duckdb caches
  (v1.3.0 + v1.5.2).

## QA-002 — direct helper matches() None-arg crash

`functions/string.py::matches()`: None regex now returns an empty
collection; non-String regex raises typed `FHIRPathFunctionError`
(previously raw `TypeError: object of type 'NoneType' has no len()`).
6th instance of the exported-helper-API family.

## QA-003 — DEFERRED (dialect)

Mid-pattern inline flags (`a(?i)B`), scoped flag groups (`(?i:a)b`), and
regex-level `\uXXXX` escapes diverge (Python re supports; std::regex and
default PCRE do not). Spec note: dialect not prescribed. Pinned in the
extended divergence test.

## Regression coverage

- `test_string_transform_parity.py::
  test_string_transform_replace_matches_named_group_spec_example_fp10_skeptic`
  upgraded to full native+fallback parity (10 cases incl. the verbatim
  §5.6.10 pattern, mixed $N/${name}, ${unknown}/$name literals, matches()
  with named groups, inline-flag combination, multiline path).
- `test_string_transform_regex_dialect_documented_divergences_fp10_skeptic2`
  extended with the 3 new divergence pairs.
- `tests/unit/test_string.py::test_matches_none_and_non_string_regex_arg_fp10_historian`.

## Validation

- Probe: 107 dual-path cases → 3 diffs, all pinned dialect divergences.
- String suites 141/141 passed.
- Full fhir4ds/fhirpath tree + full conformance: see architect handoff.
