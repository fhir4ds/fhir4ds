# QA Handoff - Iteration 8, Domain 10

Personality: HISTORIAN
Domain: 10 - Installation and Environment

## Scope

Focused on release version consistency, import health, native extension status,
forced Python fallback parity, repeated `register()` idempotency, wheel metadata,
and release-facing install snippets.

## Finding

`QA-005` HIGH API_CONTRACT: the active release target is `0.0.7`, but package
metadata, root and subpackage `__version__` constants, and notebook install
snippets still reported or installed `0.0.6`.

## Validation

- `python3 -m pytest fhir4ds/tests/test_version.py -q`: 2 passed.
- Import/register idempotency probe reported all public versions as `0.0.7`
  and repeated `fhir4ds.register()` succeeded.
- Native versus forced Python fallback probe matched for FHIRPath text, FHIRPath
  number, and CQL `ToQuantity`.
- `python3 -m build --wheel --no-isolation`: built
  `dist/fhir4ds_v2-0.0.7-py3-none-any.whl` and bundled both DuckDB extensions.
- Wheel metadata check reported `Name: fhir4ds-v2`, `Version: 0.0.7`, and both
  extension binaries present.
- System-site venv wheel smoke imported `fhir4ds`, loaded native extensions, and
  evaluated a sample `fhirpath_text`.
- `pip check` failed only on unrelated global environment packages outside
  fhir4ds.
