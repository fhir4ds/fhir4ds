# Architect Handoff — SOF-VD-13 (HISTORIAN iteration 1, 2026-08-24)

## Golden standard (scope: viewdef cnl/extra_fields)
Severity fidelity to the official SD; warnings via the validate_view_definition
pattern; lexical rules localized in types.py validators; extra_fields as a
lossless transport; builtin precedence via the constants.py registry; no
fixture-specific hacks. (Full text: .temp/architect/golden_standard.md)

## Audit of the QA-001 fix
- `cnl1_url_warning` (types.py) + consumption in parser.validate_view_definition
  mirrors the established cnl-0 warning pattern exactly — errors at parse for
  lexical/type rules, warnings returned from the permissive validator. No
  warnings-module side effects. Clean layering: parser adds no lexical logic.
- `validate_canonical_string` retains error-level checks (non-empty, `^\S*$`);
  only the cnl-1 regex miss was demoted, and the demotion is documented in both
  the docstring and AGENTS.md doctrine. profile/meta.profile paths untouched.
- No hardcoding, no fixture-specific branches; helper is field-name
  parameterized. Footprint: 2 source files, 1 test file.

## QA quality gate
QA (HISTORIAN) was sufficient: primary-source spec evidence (official SD XML
from FHIR/sql-on-fhir-v2; sql-on-fhir.js v2.0.0 reference implementation
cloned and inspected; build.fhir.org CanonicalResource), targeted probes on
all mandated angles (multi-round-trip extra_fields with mutations, XHTML
entities, warning dedup semantics, unknown-key boundary, builtin/constant
shadowing matched against RI `Object.assign` order). RETRY_QA not set.

## Empirical validation (final tree, PYTHONPATH=/mnt/d/fhir4ds)
- viewdef pytest: 1240/1240
- Official ViewDefinition suite: 144/144 (report schema PASSED)
- Master gate: ViewDefinition 144, FHIRPath 935, CQL 1706, DQM 47,
  OVERALL 2832/2832 (100.0%) — baseline held, no regressions.
- fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a, identical
  in repo bundle and ~/.local site-packages (Python-only fix; binaries
  untouched).

## Disposition
- QA-001 RESOLVED and VERIFIED. Zero non-terminal CRITICAL/HIGH/MEDIUM issues.
  iteration 1 >= min_iterations 1 -> CLEAN exit, workflow=null.
