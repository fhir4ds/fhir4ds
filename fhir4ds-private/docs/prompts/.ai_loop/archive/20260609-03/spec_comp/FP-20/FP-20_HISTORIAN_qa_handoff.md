# QA Handoff — FP-20 HISTORIAN

Personality: HISTORIAN
Phase: QA

Scope covered:
- FHIRPath N1 §9 environment variables.
- §10 reflection through `type().namespace` and `type().name`.
- §11 type-safety singleton errors for `is` / `as`.
- §12 formal grammar boundaries for external constants and qualified type specifiers.
- Native C++ DuckDB registration compared against forced Python fallback.

Fresh probe:
- `.temp/qa/fp20_historian_probe.py`

Finding:
- `QA-001` MEDIUM: native C++ rejects formal grammar external constants when
  hidden whitespace or comments appear between `%` and the identifier/string
  payload, e.g. `% 'ucum'`, `%/*grammar*/'ucum'`,
  `%//grammar\n'ucum'`, and `% \`context\`.id`.
- Forced Python fallback accepts those expressions and evaluates them correctly.
- Spec basis: the formal grammar defines `externalConstant` as `%` followed by
  an identifier or string, while whitespace and comments are hidden lexical
  tokens.

State:
- `evolution.json` updated with `QA-001`.
- Next phase: FIX.
