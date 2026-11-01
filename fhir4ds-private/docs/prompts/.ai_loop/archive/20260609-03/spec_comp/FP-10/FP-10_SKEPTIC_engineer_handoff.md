# Engineer Handoff - FP-10 SKEPTIC

Resolved issues: `QA-001`, `QA-002`, `QA-003`, `QA-004`.

Spec grounding: FHIRPath Normative Release §5.6.6-§5.6.12 defines exact
signatures for the string transform functions and §5.6 states these functions
operate on singleton String input, with multi-item input signaling an error.

Changes made:

- Native C++ `evalFunction` now rejects wrong arity for
  `upper()`, `lower()`, `replace(pattern, substitution)`, `matches(regex)`,
  `replaceMatches(regex, substitution)`, `length()`, and `toChars()`.
- Native `matches`, `replace`, and `replaceMatches` now evaluate ordinary
  transform arguments against the outer invocation focus for sourced calls, so
  sibling fields such as `pattern`, `sub`, and `regex` resolve correctly.
- Native transform helpers validate concrete String arguments and regex safety
  before input-empty short-circuiting can hide invalid expressions. Invalid
  regex compilation now raises a typed spec error instead of returning empty
  inside the helper. The native overlong-regex limit is aligned to the Python
  guard at 1000 characters.
- Forced Python fallback `length()` now enforces singleton String input through
  `ensure_string_singleton()`.
- Forced fallback `fhirpath_is_valid()` now statically validates FP-10 arity,
  obvious literal argument types, literal unions, and dangerous literal regex
  patterns.
- Added parity coverage in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py`
  and native sqllogictest coverage in `extensions/fhirpath/test/sql/fhirpath.test`.

Validation:

- Fresh probe: `python3 .temp/qa/fp10_skeptic_probe.py` -> 41 cases, 0 failures.
- Focused pytest: `109 passed`.
- Native extension sqllogictest: `462 assertions passed`.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

No new issues were discovered during remediation.
