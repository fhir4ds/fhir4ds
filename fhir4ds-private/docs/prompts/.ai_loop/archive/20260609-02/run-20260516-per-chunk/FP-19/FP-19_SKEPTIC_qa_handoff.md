FP-19 SKEPTIC QA handoff

Scope probed: FHIRPath §7 aggregate and §8 lexical elements across native DuckDB, forced Python fallback DuckDB, and direct Python core where applicable. Fresh probes live in `.ai_loop/.temp/qa/fp19_probe.py`.

Spec anchors checked:
- FHIRPath N1 §7.1: `aggregate()` evaluates the aggregator once per input item with `$this`, `$index`, and `$total`; `$total` starts from `init` or empty.
- FHIRPath N1 §8.1/§8.2: whitespace only delimits tokens; single-line and block comments are ignored.
- FHIRPath N1 §8.5/§8.7: keywords are case-sensitive.
- FHIRPath N1 §8.6: delimited identifiers may contain otherwise invalid characters, and FHIRPath string escapes also work inside them.

Findings:
- FP19-SK-001 HIGH: Escaped backticks in delimited identifiers are broken. Native rejects `` `back\`tick` `` as invalid; Python parses it but does not unescape it to the model key.
- FP19-SK-002 MEDIUM: Direct Python core parsing accepts only a valid prefix for `1 Month`, returning `[1]` instead of rejecting the full expression. This violates case-sensitive keyword/quantity lexical handling and creates a public direct-core discrepancy from native/fallback wrappers.

Clean checks during QA:
- Existing focused parity file `fhir4ds/fhirpath/duckdb/tests/integration/test_aggregate_lexical_parity.py` passed before remediation, but it did not cover escaped delimited identifiers or direct-core trailing-token rejection.
