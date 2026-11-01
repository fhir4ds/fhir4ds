# QA Handoff - FP-16 HISTORIAN

Scope: systematic FHIRPath Section 6.4 coverage for `|`, `in`, and infix
`contains` after the SKEPTIC fix.

Spec basis: union removes duplicates by FHIRPath equality. `in` returns empty
for empty left, false for empty right, and errors for multi-item left.
`contains` is the converse: empty right returns empty, empty left returns
false, and multi-item right is an error.

Probe: `.temp/qa/fp16_historian_probe.py` encoded expected outputs for native
and forced fallback registrations over numeric, string, temporal, Quantity,
and complex JSON values, including invalid singleton operands and valid
multi-item collection operands.

Result: no new issue found. The probe reported `FAILURES 0`.
