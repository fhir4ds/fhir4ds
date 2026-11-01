# QA Handoff — FP-01 SKEPTIC

Scope: FHIRPath §4.1 literals, with native DuckDB/C++ vs forced Python fallback comparisons.

Spec grounding:
- FHIRPath §4.1 lists Boolean, String, Integer, Decimal, Date, Time, DateTime, and Quantity literals.
- §4.1.2 string literal handling processes `\uXXXX` escapes as Unicode code units; current published text says valid UTF-16 surrogate pairs combine into one Unicode scalar value.
- §4.1.8 defines Quantity as a number followed by a UCUM string unit or calendar duration keyword; the formal grammar is `quantity: NUMBER unit?`, so hidden whitespace is not required.

Hypotheses probed:
- Date/Time component validation and timezone offset boundaries could diverge between native and fallback.
- Invalid numeric suffixes (`1e2`, `1.`, `.1`, `1foo`) could be accepted as valid prefixes.
- Calendar duration quantities without whitespace (`1day`) could regress.
- Quoted UCUM quantities without whitespace (`10'mg'`) could diverge.
- Unicode escape handling could mishandle surrogate pairs.

Findings:
- `QA-FP01-001` MEDIUM: forced Python fallback rejects valid no-whitespace quoted UCUM Quantity literal `10'mg'`, while native accepts it and the formal grammar permits it.
- `QA-FP01-002` MEDIUM: valid surrogate-pair string literal `'\uD834\uDD1E'` does not materialize as a single Unicode scalar value and DuckDB result UDFs error/fail serialization.

Evidence:
- Probe script: `.temp/qa/fp01_skeptic_probe.py`
- Probe output: `.temp/qa/fp01_skeptic_probe.json`

No source code was modified during QA beyond local knowledge/state/handoff files.
