# Architect Handoff: CQL-11 SKEPTIC

Golden standard written to `.temp/architect/golden_standard.md`. The audit
checked the CQL Arithmetic Part 2 remediation against the parser, translator,
Python fallback UDF, C++ no-Python helper, and parity test boundaries.

Result: PASS. No new architectural findings and no `RETRY_QA` veto. QA was
adequate for the SKEPTIC role: it tested malformed Quantity JSON, integer vs
decimal Quantity stepping, negative/tie arithmetic behavior, divide/modulo
null cases, temporal precision boundaries, dynamic FHIR `valueString`
exclusion, public helper surfaces, translated CQL, native-loaded registration,
forced Python fallback, and no-Python C++ checks where relevant.

Verified issues: 2 HIGH `SPEC_VIOLATION` findings. `QA-001` fixed
integer-authored Quantity predecessor/successor stepping by preserving literal
shape and choosing step `1` instead of `1e-8`. `QA-002` fixed Python public
predecessor/successor handling so malformed Quantity JSON numeric strings
return SQL NULL instead of being coerced.

Structural assessment: the fix is localized to the correct boundaries. Parser
and translator changes preserve authored Quantity literal shape without
introducing resource/profile/measure-specific behavior. Python and C++ helper
changes enforce strict Quantity JSON shape at public row-resilient SQL helper
surfaces. The rebuilt bundled CQL extension keeps no-Python/native behavior in
sync with forced Python fallback.

Validation passed: `.temp/qa/cql11_skeptic_probe.py`; focused CQL-11
arithmetic part 2 parity pytest 7/7; adjacent arithmetic/no-Python pytest
12/12; full conformance 2822/2822.

Recommended next phase: clean exit to the outer spec compliance orchestrator.
