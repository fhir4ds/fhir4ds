# QA Handoff — FP-01 HISTORIAN

## Scope

SPEC COMPLIANCE CHUNK FP-01: FHIRPath §4.1 Literals. Fresh HISTORIAN pass,
using only the current source tree and current state. I verified the normative
literal text against the HL7 FHIRPath source at
`https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md`.

Relevant spec summary: FHIRPath defines Boolean, String, Integer, Decimal,
Date, Time, DateTime, and Quantity literals. String literals are single-quoted,
UTF-8 strings; `\uXXXX` escape sequences are UTF-16 code units, and surrogate
code units must be paired into one Unicode scalar value. Date, Time, and
DateTime literals must obey the documented partial ISO forms; Time has no
timezone offset. Quantity literals are numeric values followed by quoted UCUM
units or case-sensitive calendar duration keywords.

## Fresh Probe

Created and ran `.temp/qa/fp01_historian_fresh_probe.py`. It builds a native
C++ DuckDB connection and a forced Python fallback connection, then compares
literal validity and public UDF outputs across Boolean, String, Integer,
Decimal, Date, Time, DateTime, and Quantity cases.

## Finding

`QA-001` MEDIUM, OPEN: unpaired Unicode surrogate string escapes are accepted
and then surface as backend-specific runtime failures.

Reproducer:

```sql
SELECT fhirpath_is_valid('''\uD834''');
SELECT fhirpath('{"resourceType":"Patient"}'::JSON, '''\uD834''');
SELECT fhirpath_text('{"resourceType":"Patient"}'::JSON, '''\uD834''');
SELECT fhirpath_json('{"resourceType":"Patient"}'::JSON, '''\uD834''');
```

Observed:

- Native: `fhirpath_is_valid` returns `true`; result UDFs throw DuckDB
  `Invalid unicode detected in value construction`.
- Forced Python fallback: `fhirpath_is_valid` returns `true`;
  `fhirpath` / `fhirpath_text` throw pybind cast errors; `fhirpath_json`
  returns NULL.

Expected:

- `fhirpath_is_valid` returns `false` because the string literal is invalid
  under §4.1.
- Public result UDFs should not materialize invalid Unicode into DuckDB
  values; malformed-literal paths should be row-resilient empty/NULL where the
  wrapper contract applies.

## Non-Bugs Discarded

- `True` is not a Boolean literal, but it is a syntactically valid identifier
  expression, so `fhirpath_is_valid('True') = true` is acceptable.
- Calendar quantity output preserving `4 days` rather than normalizing to
  `4 'd'` is not a literal parsing defect; the literal is accepted and
  native/fallback outputs match.
- Generic syntax errors such as `1e2` may propagate through result UDFs; that
  was not logged as the FP-01 issue because the confirmed spec defect is the
  string escape validator accepting an invalid literal.

## Validation Run

- `python3 .temp/qa/fp01_historian_fresh_probe.py` currently fails only because
  `QA-001` remains open and because the probe still encodes the expected fixed
  behavior for that case.
