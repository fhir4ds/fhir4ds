# QA Handoff - FP-18 EXPLORER

Scope: FHIRPath §6.6 Math Operations and §6.7 Date/Time Arithmetic.

Normative basis checked from the official FHIRPath Normative Release v2.0.0:
- §6.6 requires singleton, type-compatible math operands; empty operands propagate; quantity units must be respected; `div` is truncated division; `mod` is the remainder of truncated division; `&` treats empty as an empty string.
- §6.7 permits Date/DateTime/Time plus or minus time-valued Quantities with unit restrictions and partial-precision truncation.
- §4.1/§8 define date/time literals and operators as lexical elements; whitespace around `+` is not a semantic precondition.

Fresh probes:
- Added and ran `.temp/qa/fp18_explorer_public_probe.py` against public DuckDB UDF surfaces: `fhirpath`, `fhirpath_text`, `fhirpath_json`, `fhirpath_bool`, `fhirpath_number`, `fhirpath_date`, `fhirpath_timestamp`, `fhirpath_quantity`, and `fhirpath_is_valid`.
- Independently compared loaded native C++ and forced Python fallback paths.
- Covered negative `div`/`mod`, division by zero, `&` empties, singleton errors, Quantity path arithmetic, FHIR temporal path values, partial Date/DateTime/Time literals, timezone preservation, leap-day/month-end arithmetic, reversed date arithmetic, and no-whitespace temporal operators.

Finding:
- QA-001 MEDIUM: native C++ rejects no-whitespace temporal arithmetic after Time/DateTime literals (`@T23+119 minutes`, `@2016-02-29T23+119 minutes`) while forced Python fallback accepts and evaluates them. Expected results are `T00` and `2016-03-01T00`.

Additional observations for remediation:
- Negative decimal `div`/`mod` parity is worth locking in focused tests. Current C++ source appears to have the right decimal-source-text handling, but public bundled behavior should be verified after rebuild.
- Mismatches on arbitrary non-FHIR field names like `d + 1 day` were not logged as public spec failures; FHIR typed paths such as `effectiveDate`, `effectiveDateTime`, and `effectiveTime` already behave correctly in both paths.
