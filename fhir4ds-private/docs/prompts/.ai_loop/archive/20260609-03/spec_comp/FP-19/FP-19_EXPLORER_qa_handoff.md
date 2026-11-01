# QA Handoff — FP-19 EXPLORER

Scope: FHIRPath N1 Section 7 aggregates and Section 8 lexical elements, focused
on pathological combinations after SKEPTIC/HISTORIAN. I tested native-loaded
DuckDB/C++ against the forced Python fallback with a fresh probe covering nested
aggregates, aggregate inside filters/selects, comments as token separators,
delimited identifier escapes, keyword-like identifiers, strict whitespace, and
numeric/quantity lexical edges.

Finding:

- `QA-001` MEDIUM `SPEC_VIOLATION`: native `fhirpath_is_valid()` accepted
  invalid `aggregate()` arities. Reproducers:
  `a.aggregate()`, `a.aggregate($this, 0, 1)`, `aggregate()`, and
  `aggregate($this, {}, {})` returned true natively but false in the forced
  Python fallback. FHIRPath N1 Section 7.1 defines exactly one aggregator
  expression plus optional `init`.

Fresh QA evidence:

- `.temp/qa/fp19_explorer_probe.py` initially reproduced the native/fallback
  validity drift, then passed after remediation with 30 parity cases and 25
  validity cases.
- No additional issues were found in the explored comment, delimited
  identifier, keyword, case-sensitivity, or no-whitespace quantity cases.
