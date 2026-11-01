# Engineer Handoff — FP-10 (iteration 1)

All 5 CONFIRMED issues RESOLVED; QA-004 DEFERRED (spec-sanctioned dialect
difference). Triage: QA-001/002/003 PARITY, QA-005/006 SPEC_VIOLATION
(API_CONTRACT for the helper).

## Changes

Native (extensions/fhirpath/src/fhirpath/evaluator.cpp; extension rebuilt via
`cmake --build . --target fhirpath_loadable_extension` and redeployed to
fhir4ds/fhirpath/duckdb/extensions/ + ~/.duckdb caches v1.3.0/v1.5.2):
- QA-001: non-multiline unescaped `$` → zero-width `(?=\n?$)` (PCRE
  trailing-newline semantics) in normalizeFHIRPathRegex.
- QA-002: new `applyInlineRegexFlags` folds leading (?i)/(?m)/(?s) into the
  flags text at fn_matches / fn_replaceMatches call sites (icase must reach
  std::regex compile options); normalizeFHIRPathRegex also strips them
  defensively before std::regex sees them.

Python fallback / helpers:
- QA-003: `fhir4ds/fhirpath/engine/invocations/strings.py` gained
  `_translate_pcre_ascii_classes` (ASCII-PCRE \w\W\dD sS\b\B + POSIX
  [[:name:]] expansion), applied inside `_compile_regex`; the direct helper
  `matches` shares it. re.ASCII deliberately NOT used (breaks Unicode
  case-insensitive matching).
- QA-005: `fhir4ds/fhirpath/duckdb/udf.py` — dollar-sign syntax checks
  (\$\$, $var) moved to `_INVALID_DOLLAR_PATTERNS` applied to
  `_mask_string_literals(...)` in `_get_compiled_evaluator` and
  `fhirpath_is_valid_udf`.
- QA-006: `fhir4ds/fhirpath/duckdb/functions/string.py` — replace_matches
  delegates to the engine implementation (§5.6.10 $N/${name}/$$/named-group
  contract, keeps the typed ReDoS guard); replace() validates
  pattern/replacement via `_validate_string_arg`.

## Regression coverage

- `test_string_transform_parity.py::
  test_string_transform_regex_anchor_flags_and_classes_parity_fp10_skeptic2`
  (22 dual-path cases: $-anchor, inline flags, ASCII classes, $$) and
  `..._regex_dialect_documented_divergences_fp10_skeptic2` (lookbehind pin).
- `tests/unit/test_string.py::TestReplaceMatches` — 4 new fp10_skeptic2
  tests (dollar substitution syntax, None-arg contracts, ASCII dialect).

## Validation

- String suites: 140/140 passed.
- Probes: 82-case dual-path probe down to 1 diff (lookbehind, DEFERRED);
  31-case class probe down to 1 diff (bare [:alpha:] corner, dialect pin).
- Full fhir4ds/fhirpath pytest tree and full conformance run: see
  architect handoff (run after fixes).
