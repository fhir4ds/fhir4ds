# Remediation Handoff - Iteration 8, Domain 10

## Fixed

Resolved `QA-005` by bumping package metadata, root/subpackage public version
constants, and notebook install snippets from `0.0.6` to `0.0.7`. Added a
version regression that compares `pyproject.toml` project metadata to
`fhir4ds.__version__`.

## Tests Added

- `test_pyproject_version_matches_public_root_version`

## Validation

Version tests, import/register idempotency, native/fallback parity, wheel build,
wheel metadata/contents inspection, and wheel smoke import all passed. `pip
check` exposed unrelated shared-environment dependency issues, not fhir4ds
metadata problems.
