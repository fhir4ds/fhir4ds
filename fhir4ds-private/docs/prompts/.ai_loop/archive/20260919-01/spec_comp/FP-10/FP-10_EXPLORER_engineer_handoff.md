# Engineer Handoff — FP-10 EXPLORER iteration 1 (2026-08-17)

## QA-001 (MEDIUM, SPEC_VIOLATION) — RESOLVED

Reproduced: `p.replace('\\','/')` (resource `{"p":"C:\\x\\y"}`) parsed and
evaluated natively (`['C:/x/y']`) but raised FHIRPathSyntaxError in the
Python/antlr fallback; `fhirpath_is_valid` diverged (True vs False). Lexer
token trace showed ONE STRING token whose text spanned the closing quote and
the comma: with a raw backslash allowed in the STRING loop and ESC also
matching `\'`, antlr maximal munch completed a LONGER string through the
escaped-quote path, swallowing the argument boundary.

### Fix (root cause, Python-side only)
- `fhir4ds/fhirpath/parser/FHIRPath.g4`: STRING loop is now NON-GREEDY
  (`'\'' (ESC | ~['])*? '\''`), closing the literal at the first quote that
  terminates any alternative path. Regenerated
  `fhir4ds/fhirpath/parser/generated/` (Lexer/Parser/Listener/Visitor,
  .tokens, .interp) with antlr4 4.13.1 (runtime 4.13.2 compatible).
- Native C++ lexer was already correct — no extension rebuild required.

### Recovery-Gate note (important doctrine)
First attempt aligned STRING with the official grammar (negated set
excluding backslash). It fixed the bug but broke two TOLERATED raw-backslash
corners the native engine accepts and tests pin (`'abc\'` → "abc",
`'short \u005'` → "short u005"). Reverted; the non-greedy form fixes the
mis-lexing class without narrowing tolerance. LESSON: when a grammar fix
touches lexer ambiguity, rerun the literal-parity file BEFORE the full tree.

### Regression coverage
- `fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py::
  test_escaped_backslash_argument_literals_lex_correctly_fp10_explorer`
  (native + forced fallback outputs for 7 cases incl. tolerant corners,
  plus is_valid parity).

### Validation
- fhirpath pytest tree: 1774 passed (0 failed).
- viewdef pytest tree: 1118 passed.
- Full conformance: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47 — OVERALL 2832/2832 (baseline held).

No new issues discovered during remediation. All issues terminal.
