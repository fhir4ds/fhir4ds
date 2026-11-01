# Engineer Handoff — SOF-VD-13 (HISTORIAN iteration 1, 2026-08-24)

## Triage
| Issue | Category | Severity | Action |
|---|---|---|---|
| QA-001 cnl-1 severity | SPEC_VIOLATION | MEDIUM | RESOLVED |

## QA-001 remediation
- Root cause: `types.py:validate_canonical_string` raised ValueError on any
  cnl-1 regex miss for `ViewDefinition.url`, surfaced as a parse ParseError.
  The official StructureDefinition-ViewDefinition (FHIR/sql-on-fhir-v2,
  element ViewDefinition.url) declares cnl-1 with `severity=warning`
  (source MetadataResource), and the sql-on-fhir.js v2.0.0 reference
  implementation does not check url characters at all.
- Fix (minimal, spec-grounded):
  - `fhir4ds/viewdef/types.py`: `validate_canonical_string` now enforces only
    the error-level lexical rules (non-empty string, `^\S*$` uri whitespace
    rule). New `cnl1_url_warning(url, field_name)` returns the WARNING message
    for cnl-1 misses (or None).
  - `fhir4ds/viewdef/parser.py`: `validate_view_definition` appends the
    cnl-1 warning, mirroring the existing cnl-0 warning pattern.
  - `fhir4ds/viewdef/tests/unit/test_parser.py` (TestCnl1CanonicalUrlInvariantPerSpecG1):
    pipe/hash/`|version` urls now assert parse + warning + to_dict round-trip;
    whitespace url still asserts ParseError (uri lexical rule); clean url
    asserts no cnl-1 warning.
- Reproducer (passes): url `http://example.org/vd|1.0` parses, warns via
  validate_view_definition, round-trips through to_dict; `http://x/v d` still
  raises ParseError.
- Note: profile[]/meta.profile[] paths unchanged (canonical form with |version
  still accepted, whitespace rejected).

## Validation (fresh runs, final tree, PYTHONPATH=/mnt/d/fhir4ds)
- viewdef pytest: 1240/1240 passed (was 1238; +2 net new assertions/tests).
- Official ViewDefinition conformance suite: 144/144 (100.0%), report schema
  validation PASSED.
- Master gate run_all.py: see architect handoff (run concurrently).
- Binary md5 (unchanged by this Python-only fix):
  fhirpath.duckdb_extension = 57d0634b6ee6eddee9fc06a1355bef5a
  (repo bundle == ~/.local site-packages copy).

## Terminal states
- QA-001: RESOLVED (fix + focused regression tests + gates green).
