# Architect Handoff — FP-10 EXPLORER launch (2026-08-17)

## Scope audited
This launch's delta only (FP-01..FP-10 cumulative campaign diff otherwise
audited by prior launches and the milestone code review):
- `fhir4ds/fhirpath/parser/FHIRPath.g4` (+9: STRING loop made non-greedy,
  with an explanatory comment)
- `fhir4ds/fhirpath/parser/generated/FHIRPathLexer.py` + `.interp`
  (regenerated, minimal DFA delta; Parser/Listener/Visitor byte-identical
  to committed versions after regenerating WITH `-visitor`)
- `test_string_transform_parity.py` (+1 regression test)
- AGENTS.md / GLOBAL_KNOWLEDGE.md documentation rows

## Golden-standard invariants checked
1. Dual-engine lockstep: fix is Python-only because the native C++ lexer was
   already correct; parity verified at UDF, core-engine, and is_valid levels.
   ✔
2. No workaround shims: the fix is in the grammar itself (root cause), not a
   pre/post-parse patcher. An official-grammar alignment variant was
   attempted and REVERTED via the Recovery Gate (broke native-pinned
   tolerant corners) — the retained fix preserves tolerance while killing
   the mis-lexing class. ✔
3. Generated-artifact hygiene: antlr4 tool version (4.13.1) matches the
   committed generated header; regeneration with `-visitor` restored the
   41 `accept()` visitor methods the first (flag-less) regeneration dropped
   — caught by diff-stat audit; final generated diff is minimal. ✔
4. Baseline protection: conformance 2832/2832 (ViewDef 144, FHIRPath 935,
   CQL 1706, DQM 47); fhirpath pytest tree 1774 passed; viewdef tree 1118
   passed. ✔
5. No silent fallbacks, no new hardcoding, no cross-layer reach-through.
   ✔

## QA quality gate (EXPLORER, iteration 1)
Adequate — 69 adversarial dual-path cases covering the mandated boundaries
(locale case mappings, astral/ZWJ code points, greedy/lazy, multiline
anchors, field-sourced regex, transforms in where/select/repeat, chained
transforms, is_valid), 1 real bug found and fixed with a guard test. No
RETRY_QA.

## Issues
QA-001 (MEDIUM, RESOLVED, verified iteration 1) — tombstoned in
evolution.json; full detail in ARCHIVE_LOG entry below and
engineer_handoff.md.

## Structural health: GOOD. Chunk FP-10 CLOSED (SKEPTIC 5+1 DEFERRED,
HISTORIAN 2+1 DEFERRED, EXPLORER 1). Clean exit at min_iterations=1; zero
non-terminal CRITICAL/HIGH/MEDIUM issues remain.

## Archive note (QA-001)
Repro: `p.replace('\\','/')` on `{"p":"C:\\x\\y"}` → native `['C:/x/y']`,
fallback FHIRPathSyntaxError; is_valid True vs False. Root cause: antlr
STRING loop's raw-backslash alternative + ESC `\'` enabled maximal munch to
swallow the closing quote and comma (one token `'\\','`). Fix: non-greedy
loop in FHIRPath.g4; regenerate with
`antlr4 -Dlanguage=Python3 -visitor -o generated FHIRPath.g4`.
