# Architect Handoff — FP-07

Structural audit result: healthy for this chunk after remediation. The bug was localized to a boundary-validation lapse in native C++ decimal parsing, not a broad architectural breakdown. The correct architecture is now explicit: conversion functions must validate FHIRPath lexical/type tables before delegating to permissive host parsers (`std::stod`, Python `Decimal`, `datetime.fromisoformat`, etc.), and public native behavior must be parity-tested against forced Python fallback after every native source change.

Issues by category:
- SPEC_VIOLATION: 1 found, 1 resolved and verified (`QA-001`).
- REGRESSION_RISK: no open issue; mitigated by native SQL and Python/native parity regressions.

QA quality check: adequate. SKEPTIC tested unhappy lexical decimal cases, native vs forced fallback, Date/DateTime invalidity, singleton/multi-item resilience, and public DuckDB UDF surfaces. No `RETRY_QA` needed.

Residual risk: native decimal values are still represented internally as `double`, so display precision/trailing-zero preservation can differ from Python `Decimal` for accepted values such as `12.30`. This is adjacent to the existing documented numeric precision limitation and was not expanded in FP-07.
