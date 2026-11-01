# QA Handoff — SOF-VD-02 SKEPTIC (constants)

## Verdict: CLEAN — 27/27 fresh dual-path cases (0 parity diffs; 3 checker-side expectation fixes)

All 20 primitive value[x] happy paths verified (bool/string/code/integer/decimal/uri/url/
canonical/id/date/instant/dateTime/time/oid/base64/positiveInt/unsignedInt/integer64-as-
JSON-string) with %name substitution in column paths and where filters; backtick %`name`
form substituted. Invalid shapes raise identically on BOTH engines: unknown %name ref →
ValidationError; empty valueString → ParseError; valueInteger 3.0 → ParseError (FHIR int
rep stricter than Ajv); valueInteger64 out of FHIRPath int32 range → ParseError;
dual-value[x] → ParseError; missing value[x] → ParseError; bad sql-name (_bad) → ParseError.
Population surface renders boolean columns as 'true'/'false' strings and numerics as
strings — norm() normalization applied in checker.

Adjudications (probe-expectation fixes, no defects): wants initially had patient_id
columns the single-column views don't project; instant/time constants are temporal
VALUES — string functions need .toString() wrap (CQL-12/sweep doctrine); instant direct
contains() renders false (row artifact) → replaced with toString() equality.

Evidence: .temp/qa/speccomp2/sofvd02_skeptic_probe1.py (flagged=0)
