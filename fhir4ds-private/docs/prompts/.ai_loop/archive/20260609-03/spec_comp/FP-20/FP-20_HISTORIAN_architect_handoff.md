# Architect Handoff — FP-20 HISTORIAN

Structural audit result:
- PASS. The remediation is localized to native lexical tokenization and aligns
  with the existing lexer abstraction: hidden tokens are consumed by
  `skipWhitespace()`, and the `%` branch now uses that same path before reading
  the external constant payload.

Golden standard:
- Updated `.temp/architect/golden_standard.md` with FP-20 HISTORIAN invariants
  for §§9-12, especially formal grammar hidden-token handling after `%`.

Issue disposition:
- `QA-001` resolved and archived in `ARCHIVE_LOG.md`.
- No new architectural findings were logged.
- `RETRY_QA` not set: QA covered the required HISTORIAN slice with a fresh
  native-vs-forced-fallback probe, focused regression coverage, formal grammar
  examples, type-reflection checks, and full conformance.

Validation:
- Fresh probe: `.temp/qa/fp20_historian_probe.py` passed 26 cases.
- Focused pytest: `test_environment_type_parity.py` passed 9/9.
- Native sqllogictest: 706 assertions passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

Recommended fix order:
- No remaining engineer work for FP-20 HISTORIAN.
