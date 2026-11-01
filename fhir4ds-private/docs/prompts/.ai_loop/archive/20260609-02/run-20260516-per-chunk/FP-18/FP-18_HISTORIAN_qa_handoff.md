# FP-18 HISTORIAN QA Handoff

Scope: FHIRPath N1 §6.6 Math Operations and §6.7 Date/Time Arithmetic.

Spec basis: The official FHIRPath N1 spec requires math operands to be singleton and type-compatible, `&` to concatenate strings while treating empty operands as empty strings, and date/time arithmetic to accept only valid units for the temporal left operand. For partial temporal values, more precise quantities are converted down to the highest precision present before addition/subtraction.

Fresh probes: `.temp/qa/fp18_historian_probe.py` compared native C++ DuckDB UDFs and the forced Python fallback across 34 public-output expressions covering `*`, `/`, `+`, `-`, `div`, `mod`, `&`, singleton-error resilience, compatible/incompatible Quantity arithmetic, partial Date/DateTime/Time arithmetic, timezone preservation, leap-day/month-end clamping, FHIR temporal path strings, and invalid duration units.

Finding: QA-FP18-HIST-001 (HIGH). Native returned `T13` for `@T12 + 61 minutes` and invalid/empty for `@T12 + 1 day`, while forced Python fallback returned `T12` for both before remediation. This violated §6.7 partial precision conversion and Time unit validation.
