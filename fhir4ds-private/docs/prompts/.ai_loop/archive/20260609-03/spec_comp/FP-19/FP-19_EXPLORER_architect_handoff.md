# Architect Handoff — FP-19 EXPLORER

Golden standard: `.temp/architect/golden_standard.md` defines the aggregate and
lexical invariants used for this audit. The key invariant for this remediation
is that native and fallback validity must agree, and arity checks must happen
before semantic dispatch so empty data cannot mask malformed calls.

Structural audit result: clean. The fix is localized to native evaluator
function dispatch and does not broaden parsing, add data-specific behavior, or
change public UDF row-resilience policy. Regression coverage is aligned across
the fresh EXPLORER probe, Python parity tests, native sqllogictest, and the
bundled extension binary.

QA quality: adequate. QA exercised the requested EXPLORER combinations:
nested aggregates, aggregate in filters/selects, comment placement, delimited
identifier escapes, keyword-like identifiers, strict whitespace, case variants,
numeric/quantity lexical edges, and native/fallback validity divergence. No
`RETRY_QA` veto is needed.

Issue summary:

- `QA-001` MEDIUM `SPEC_VIOLATION`: resolved and archived. Recommended fix
  order has no remaining items for FP-19 EXPLORER.

Validation accepted:

- Fresh probe: OK, 30 parity cases and 25 validity cases.
- Focused pytest: 7 passed.
- Native sqllogictest: 650 assertions passed.
- Full conformance: 2822/2822.
