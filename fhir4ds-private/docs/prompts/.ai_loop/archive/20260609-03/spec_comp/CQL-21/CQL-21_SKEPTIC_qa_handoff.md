# CQL-21 SKEPTIC QA Handoff

## Scope

Fresh SKEPTIC audit for CQL-21 Clinical Operators, focused on age precision
variants and backend parity for Python fallback, native-loaded registration,
and no-Python/browser-style C++ extension execution.

## Finding

- `CQL21-SKEPTIC-001` (`HIGH`, `SPEC_VIOLATION`): the no-Python compiled CQL
  extension path was missing sub-day `AgeIn*At` registrations even though
  Python fallback and native-loaded supplement paths could execute the same
  expressions. The CQL Reference Appendix B clinical operators surface includes
  `AgeInHoursAt`, `AgeInMinutesAt`, `AgeInSecondsAt`, and the corresponding
  `CalculateAgeIn*At` signatures.

## Reproducer

- `.temp/qa/cql21_skeptic_probe.py` exercises:
  - `AgeInHoursAt`, `AgeInMinutesAt`, `AgeInSecondsAt`
  - `CalculateAgeInHoursAt`, `CalculateAgeInMinutesAt`,
    `CalculateAgeInSecondsAt`
  - Python fallback, native-loaded registration, and no-Python C++ extension
    paths.

## Status

The issue is handed to remediation as a confirmed compiled-extension
registration gap.

## Final QA Clean-Exit Check

Iteration 2 rechecked the clinical age probe after remediation and architect
bookkeeping. `.temp/qa/cql21_skeptic_probe.py` still passes across Python
fallback, native-loaded registration, and no-Python C++ extension execution.
No non-terminal CRITICAL/HIGH/MEDIUM issues remain, `min_iterations` is
satisfied, and exhaustive mode is false.
