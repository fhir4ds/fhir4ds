# Code Review Findings - Release 0.0.9

## Findings

No blocking implementation, security, or regression findings were identified in
the 0.0.9 release-prep changes.

## Review Scope

- Audited the 0.0.9 version-surface patch across `pyproject.toml`, public
  `__version__` constants, notebook snippets, website version assertions,
  WASM wheel references, release notes, and regenerated browser assets.
- Scanned source-adapter SQL construction for raw interpolation risks. The
  reviewed dynamic SQL paths use `quote_identifier()`, `quote_sql_literal()`,
  parameter binding, or pre-existing cleanup/idempotency patterns.
- Inspected unrelated existing docs changes in `web/website/docs/user-guide/cli.md`
  and `web/website/sidebars.ts`; they appear to document the CQL facade and are
  not part of the 0.0.9 version remediation.

## Notes

- `web/wasm-demo/public/fhir4ds_v2-0.0.9-py3-none-any.whl` exists in the
  workspace and the old `0.0.8` wheel was removed, but Git reports the new wheel
  as untracked. Release commit preparation must include the new wheel if this
  tracked artifact remains part of the release surface.
- Website static snapshot validation passed after the 0.0.9 WASM build and
  copy step.

## Validation Reviewed

- `python3 -m pytest fhir4ds/tests/test_version.py -q --tb=short` - passed.
- `python3 -m hatch build -t wheel` - produced
  `dist/fhir4ds_v2-0.0.9-py3-none-any.whl`.
- Wheel metadata/contents smoke check - passed, including bundled native
  `fhirpath` and `cql` extensions.
- `npm run build` in `web/wasm-demo` - passed.
- `npm run typecheck` and `npm run build` in `web/website` - passed.
