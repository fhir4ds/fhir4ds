# Engineer Handoff — FP-13 launch, iteration 1 (HISTORIAN)

## QA-001 (MEDIUM, RESOLVED): string `~` whitespace class too broad + parity break
- Root cause: FHIRPath N1 §6.1.2 String Equivalence says whitespace is
  normalized "as defined in the Whitespace lexical category", which the spec
  defines as ONLY tab (U+0009), LF (U+000A), CR (U+000D), space (U+0020).
  The native `normalizeEquivalentString` (evaluator.cpp ~line 1507) admitted
  the full Unicode whitespace set (U+0085, U+00A0, U+1680, U+2000-0x200A,
  U+2028/9, U+202F, U+205F, U+3000), making `'a b' ~ 'a b'` true in
  both engines; the Python fallback's `normalize_string` used
  `str.isspace()`, which additionally admits U+001C-001F — a native-vs-
  fallback parity break (`'ab' ~ 'a b'` fallback=true native=false).
- Fix (both engines, lockstep):
  - extensions/fhirpath/src/fhirpath/evaluator.cpp: whitespace predicate in
    `normalizeEquivalentString` reduced to the four lexical-category
    codepoints, with a spec citation comment.
  - fhir4ds/fhirpath/engine/invocations/equality.py: `normalize_string` now
    uses `_FHIRPATH_WHITESPACE = frozenset("\t\n\r ")`.
- Extension rebuilt (`make fhirpath_loadable_extension`) and redeployed to
  fhir4ds/fhirpath/duckdb/extensions/ (repo bundle), /tmp/duckdb_cpp_ext/,
  and ~/.local/lib/python3.10/site-packages (md5 26937fe57ec755be...);
  ~/.duckdb extension caches cleared.
- Regression test:
  `test_string_equivalence_whitespace_lexical_category_parity_fp13_historian`
  in fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py
  (21 parametrized cases across native + forced fallback: lexical-category
  whitespace true; NBSP/U+0085/U+1680/U+2028/9/U+202F/U+205F/U+3000/
  U+001C-001F/U+200B false; `=` stays exact; `!~` mirrors).
- Validation: test_comparison_parity.py 60/60 passed (14 prior FP-13 SKEPTIC
  decimal cases + 21 new + 25 pre-existing); full conformance 2832/2832
  (ViewDefinition 144, FHIRPath 935, CQL 1706, DQM 47) — baseline held.

No other issues filed this iteration; the SKEPTIC least-precision decimal
`~` fix was re-verified regression-free in both engines before this change.
