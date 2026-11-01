# Architect Handoff: CQL-10 EXPLORER

## Decision

CQL-10 EXPLORER is accepted with 4 issues found, fixed, and verified. There
are no open issues for this personality pass.

## Architecture Notes

- Public CQL DuckDB helper functions are part of the compatibility surface.
  C++-only/browser direct helper behavior must stay aligned with native-loaded
  registration and forced Python fallback behavior.
- Boundary helpers need an explicit classifier before formatting values:
  numeric text, four-digit year date text, Date/DateTime text, and Time text
  cannot share a loose string path.
- Native temporal helpers must reject invalid dates, invalid times, impossible
  timezone offsets, and invalid Quantity JSON before arithmetic.
- Quantity/scalar translation should return SQL NULL for NULL scalar or
  Quantity values; internal Quantity JSON with a null `value` is not a valid
  arithmetic result.
- Accepted CQL translator paths must lower to executable helper calls, not
  literal SQL forms that DuckDB may reject at bind time.

## Required Regression Gates

- Native-loaded C++ and forced Python fallback DuckDB parity tests.
- C++-only/browser extension surface tests for public helper UDFs.
- Native C++ unittest after extension changes.
- CQL conformance, full conformance, and full `fhir4ds` pytest before chunk
  closure.
