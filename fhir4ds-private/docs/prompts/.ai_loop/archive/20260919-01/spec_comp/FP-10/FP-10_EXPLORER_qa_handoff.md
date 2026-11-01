# QA Handoff — FP-10 EXPLORER (iteration 1, 2026-08-17)

Chunk: FHIRPath §5.6.6-§5.6.12 String Manipulation (upper/lower/replace/
matches/replaceMatches/length/toChars). Dual-path probe (69 cases) at
`.temp/qa/fp10_explorer3_2026_08_17/probe.py`, run with
`PYTHONPATH=/mnt/d/fhir4ds` per doctrine (native connection asserts
`register_fhirpath(con) is True`; fallback forced via
`duckdb.__version__="0.0.0-forced-python-fallback"`).

## Result: 1 issue (QA-001, MEDIUM, CONFIRMED); 68/69 parity-clean

### QA-001 — grammar STRING loop admits raw backslash; maximal munch mis-lexes
`'lit\\'` + `,`
- Repro: `p.replace('\\','/')` on `{"p":"C:\\x"}` → native `['C:/x/y']`,
  fallback empty (FHIRPathSyntaxError "token recognition error at: ')'").
  Also `('a'.iif(true,'\\','x'))`, `('\\') | 'x'`; `fhirpath_is_valid`
  diverges (native True / fallback False).
- Token trace proof: `FHIRPathLexer` on `'a'.replace('\\','x')` emits ONE
  string token `'\\','` — ESC's `\'` alternative + `~[']` loop admits the
  longer greedy match, swallowing the closing quote and comma.
- Spec: official HL7 fhirpath.g4 STRING is `'\' (ESC | ~['\\']) '\''`;
  this repo uses `~[']`. DELIMITEDIDENTIFIER in the same file already
  uses the restricted form.
- Fix direction: restrict STRING loop to `~['\\]`, regenerate antlr
  Python lexer/parser (`antlr4` CLI available), rerun fhirpath tree +
  full conformance (baseline 2832/2832). Check tolerated bare `\d`-style
  literals in tests/fixtures for fallout.

### Verified clean (do not "fix")
- Locale-sensitive case mapping: Turkish ı→I, İ→i+U+0307, Σ→σ (context-free),
  ς→Σ, Cyrillic, fullwidth Ａ↔ａ — parity in both engines.
- toChars/length code-point semantics: astral 😀x😀=3, ZWJ family=5,
  regional-indicator flags=2, combining élé=5; consistent with FP-09
  substring/indexOf code-point positions (`emoji.substring(0,1)='😀'`,
  `indexOf('x')=1`).
- replaceMatches: greedy vs lazy (`<.*>`/`<.*?>` on `<a><b>`), adjacent
  captures `$2$1`→'baaa', optional-group `(a)(b)?`, 4-group reorder →
  '4321', two-digit `$10`→'' (both engines), `(?m)` line-wise
  replaceMatches on 3-line input, `(?s)`, `(?i)` leading flags,
  regex FROM resource field (`letters.matches(pat)` with `pat="\\d+"`).
- matches: partial-match semantics, `$` anchors with/without multiline,
  'abc\n'.matches('(?m)^abc$') true (SKEPTIC fix intact).
- Nested quantified groups `(a+)+b` → empty in BOTH engines (shared ReDoS
  guard; intended).
- replace(): literal all-instances, non-rescan 'aaa'.replace('aa','b')
  → 'ba', astral/substitution-removal corners.
- Transforms inside where/select/repeat over resource collections
  (names/given upper/lower/length/replace/toChars chains), chained
  transforms (`long.lower().replace(' ','_').length()`,
  `upper().replaceMatches(...)`), empty/multi-item/non-String/wrong-arity
  corners → empty identically in both engines.
- `max()` unknown in fallback registry (FP-02 EXPLORER doctrine intact).

Handoff to Remediation Engineer: fix QA-001 per direction above; guard
with a dual-path regression test incl. `fhirpath_is_valid` parity.
