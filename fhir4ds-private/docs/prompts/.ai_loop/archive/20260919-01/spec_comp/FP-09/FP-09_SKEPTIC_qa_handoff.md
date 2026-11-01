# QA Handoff — FP-09 SKEPTIC (iteration 1, 2026-08-17)

Chunk: FHIRPath §5.6.1–§5.6.5 String Manipulation (Search) — indexOf,
substring(start[,length]), startsWith, endsWith, contains.

## What was probed
- Probe 1 (dual-path UDF, 164 checks incl. 18 is_valid):
  `.temp/qa/fp09_skeptic_2026_08_17/probe.py` — native extension (LOAD by
  absolute path) vs forced Python fallback (`duckdb.__version__` forced +
  `register_fhirpath(con) is False` asserted), both via
  `SELECT fhirpath(?, ?)`.
- Probe 2 (direct helpers, `fhir4ds/fhirpath/duckdb/functions/string.py`):
  spec examples, bounds, UTF-8, type/singleton errors.
- Spec verified against live N1 §5.6 (hl7.org/fhirpath/N1) fetched this session.

## Coverage highlights (all PASS)
- All N1 §5.6.1–§5.6.5 examples verbatim (indexOf 1/-1/0; substring
  defg/bc/g/{}; startsWith/endsWith true/false; contains true/false).
- indexOf: first-occurrence, overlapping needles, case-sensitivity, ''→0,
  -1 not-found, longer needle, empty input/arg {}→{}, non-string
  input/arg (Integer/Boolean/Quantity) error→empty, multi-item input/arg,
  whitespace/tab/newline literals, result typed Integer, chained compare.
- UTF-8 character positions (GLOBAL_RULES mandate): 'héllo'.indexOf('l')→2,
  emoji/CJK indexOf+substring (😀ab, 日本語です) correct in BOTH paths;
  resource-driven latin1/emoji fields verified.
- substring: start=len, start>len, length overrun → remaining, length 0
  → '', empty length {} ignored (§5.5.2 override of §4.4.1), non-Integer
  start/length (1.5, '1', true, 1.0) → error→empty, max-Integer start.
- startsWith/endsWith/contains: ''-arg → true, full-equal, longer
  prefix/suffix, case-sensitivity, empty input {} → empty, '' input →
  false, empty arg {} → empty, non-string args/inputs, multi-item.
- Chaining: select/where/iif/all/count with all five functions; resource
  fields incl. multi-element name.given; contains-function vs
  contains-operator distinction (function call on multi-item → error →
  empty, per grammar).
- is_valid classification: 18 arity/type forms — parity on both surfaces.
- Direct helpers: all sibling semantics + UTF-8 + singleton/type errors.

## Issues
- QA-001 (LOW, OPEN): `index_of` missing from the direct-helper module
  `fhir4ds/fhirpath/duckdb/functions/string.py` while substring/
  starts_with/ends_with/contains are exported (FP-09 HISTORIAN
  direct-helper doctrine). API completeness gap, not a spec violation.
- QA-002 (LOW, INTENDED): `''.substring(0)` → `{}` in both engines and
  the direct helper. Spec ambiguous ("start lies outside the length");
  shared convention, no fixture pins it. Do not "fix".
- QA-003 (LOW, INTENDED): negative start/length → `{}` (both engines +
  helper), consistent with the CQL-12 Substring NULL-for-invalid-boundary
  doctrine family. Do not "fix".

## Verdict
ZERO non-terminal CRITICAL/HIGH/MEDIUM issues. Probe-expectation note:
8 initial probe "FAILs" were QA-authoring errors (wrong index arithmetic,
`'James'` ends with 's', JSON double-encoding of \u escapes) — each
re-verified correct via direct single-expression dual-path queries before
dismissal.
