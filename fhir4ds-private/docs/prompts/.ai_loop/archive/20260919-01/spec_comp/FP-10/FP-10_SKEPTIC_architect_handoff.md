# Architect Handoff — FP-10 (iteration 1, SKEPTIC launch)

## Summary (compressed handoffs)

QA (SKEPTIC): fresh 113-case dual-path audit of §5.6.6–§5.6.12 after
discovering a prior FP-10 inner launch had left fixes/tests in the tree with
no state files; spec grounded in N1 index.adoc. Found 6 issues (5 MEDIUM, 1
LOW). Engineer: all 5 CONFIRMED issues fixed root-cause (native regex
normalization ×2 + rebuild/redeploy; fallback ASCII-class translation; udf
precheck literal masking; helper delegation to engine); regression tests in
test_string_transform_parity.py (2 new tests) and tests/unit/test_string.py
(4 new tests). Validation: fhirpath tree 1773/1773 passed; full conformance
2832/2832 held.

## Golden-standard invariants audited (chunk scope)

1. Dual-engine lockstep: every semantic change in both native and fallback —
   held (native $/inline-flag fixes; fallback class-translation; shared
   helper delegation).
2. Exported direct helpers follow engine semantics, with typed errors where
   engines return row-resilient empty (FP-09 doctrine) — held
   (replace_matches delegates; ReDoS guard preserved as typed error).
3. New regex paths must pass the shared ReDoS/length guard before
   evaluation — held (applyInlineRegexFlags runs BEFORE
   validateFHIRPathRegex; class translation happens inside the guarded
   _compile_regex).
4. No hardcoded test-specific logic — translation tables are generic
   PCRE→Python data; no fixture-specific branches.
5. No silent fallbacks — helper keeps typed FHIRPathFunctionError for
   invalid args; engine keeps documented empty-on-invalid-regex parity with
   native.

## Structural notes (no action required now)

- matchesFull() (extra-spec helper) does not use the ASCII-class
  translation; it has no native counterpart, so no parity contract exists.
  If it ever gains one, route it through _compile_regex.
- Regex dialect remains std::regex ECMAScript + normalization layer natively.
  The layer now covers $, inline flags, quantifiers-on-codepoints, icase
  codepoint classes, POSIX classes; lookbehind and named groups remain
  structurally unimplementable there (documented platform limitations).
  Long-term: RE2/PCRE2 migration (already recommended in AGENTS.md).

## QA Enforcer Gate

QA was NOT lazy: hypothesis-first dialect probing (anchors, flags, classes,
substitution syntax, helper API) against a surface whose existing tests all
passed, producing 6 spec/parity findings. No RETRY_QA.

## Issues

6 total: 5 VERIFIED (QA-001/002/003/005/006), 1 DEFERRED (QA-004 lookbehind,
spec-sanctioned dialect difference). Details archived in
spec_comp/FP-10/FP-10_SKEPTIC_evolution.json and ARCHIVE_LOG.md.

## Exit

Clean exit: iteration 1 ≥ min_iterations 1; zero non-terminal
CRITICAL/HIGH/MEDIUM issues. Recommended fix order for future work: none
pending from this chunk; carry QA-004 into any future native regex-engine
migration.
