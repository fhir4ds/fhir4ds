# QA Handoff: FP-06 SKEPTIC

## Scope

FHIRPath §5.5.1 `iif`, §5.5.2 Boolean conversion, and §5.5.3 Integer conversion. Tested Python core, Python DuckDB fallback UDFs, native/C++ DuckDB extension UDFs, and direct DuckDB conversion helpers.

## Spec Basis

FHIRPath Normative Release §5.5 says conversion functions operate on singleton input collections. §5.5.1 requires lazy `iif` branch evaluation. §5.5.2 allows Boolean conversion only from Boolean, 0/1 numeric representations, and listed strings (`true/t/yes/y/1/1.0`, `false/f/no/n/0/0.0`, case-insensitive). §5.5.3 allows Integer conversion only from Integer, Boolean, and strings matching `(+|-)?\d+`.

## Findings

1. `1.0.toInteger()` and `1.0.convertsToInteger()` incorrectly returned `1`/`true` in both native and Python fallback. Decimal is not Integer-convertible under §5.5.3.
2. Native/C++ `('a'|'b').iif(true, 'yes', 'no')` returned `yes`, while Python fallback returned empty via wrapper resilience. `iif()` is in §5.5 and must reject multi-item input.
3. Direct helpers in `fhir4ds.fhirpath.duckdb.functions.conversion` used Python truthiness/truncation: examples included `to_boolean(2) is True`, `to_boolean('0.5') is True`, and `to_integer('3.14') == 3`.

## Repro Commands

- `.temp/qa/fp06_probe.py` compared native C++ and Python fallback UDF outputs.
- Manual official spec check: https://hl7.org/fhirpath/N1/ §5.5.1-§5.5.3.

## State

Issues logged in `evolution.json`: `QA-001`, `QA-002`, `QA-003`.

## Retry QA

Architect retry confirmed `ARCH-001`: native C++ accepts leading whitespace for integer string conversion while Python fallback rejects it. Reproducer outputs:

- `' 1'.toInteger()` native `(['1'], '[1]', True)`, Python fallback `([], None, None)`.
- `' 1'.convertsToInteger()` native `(['true'], '[true]', True)`, Python fallback `(['false'], '[false]', False)`.
- Control cases: `'+1'.toInteger()` and `'+1'.convertsToInteger()` pass in both backends; trailing whitespace is rejected in both.

## Final QA Exit Check

After retry remediation, all FP-06 issues are terminal. Focused native/Python fallback parity, direct helper tests, native SQL assertions, full FHIRPath pytest, and official R4 conformance passed. No non-terminal CRITICAL/HIGH/MEDIUM issues remain.
