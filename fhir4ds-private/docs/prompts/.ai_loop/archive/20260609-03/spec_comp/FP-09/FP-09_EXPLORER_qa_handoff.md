# QA Handoff - FP-09 EXPLORER

## Scope

- Chunk: FP-09
- Personality: EXPLORER
- Spec focus: FHIRPath Normative Release section 5.6.1-5.6.5 string-search functions: `indexOf`, `substring`, `startsWith`, `endsWith`, and string-function `contains`.
- Spec grounding: section 4.5 defines singleton evaluation errors for multi-item arguments, section 5.6.1 and section 5.6.2 require singleton String/Integer arguments and empty propagation, and section 6.4.1 says union eliminates duplicate values.

## Probe

Created and ran `.temp/qa/fp09_explorer_probe.py` against both the bundled native C++ DuckDB extension and a forced Python fallback connection. The 41-case probe covered dynamic arguments, UTF-8 code-point positions, empty search terms, negative/out-of-range substring indexes, nested invocation focus, empty/multi-item inputs, invalid arity, non-string inputs, and literal union arguments.

## Finding

- `QA-001` MEDIUM: forced Python fallback `fhirpath_is_valid()` mishandled literal union arguments for FP-09 functions.
  - Missed invalid multi-item Integer unions for `substring`: `s.substring((1|2))` and `s.substring(1,(1|2))` returned `true` in fallback validation while native returned `false`.
  - Falsely rejected deduplicated singleton string unions: `s.indexOf(('a'|'a'))` returned `false` in fallback validation while native returned `true`.
  - Public result UDFs were row-resilient and already matched; the drift was in validation semantics.

## Evidence

- Before fix: `.temp/qa/fp09_explorer_probe_before_fix.log`
- After fix: `.temp/qa/fp09_explorer_probe_after_fix.log`

## Handoff

Proceed to remediation. Fix should be limited to Python fallback validation prechecks; native C++ behavior is already correct for this finding.
