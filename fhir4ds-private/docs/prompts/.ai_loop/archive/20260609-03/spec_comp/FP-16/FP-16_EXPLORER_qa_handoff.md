# QA Handoff - FP-16 EXPLORER

Scope: pathological FHIRPath Section 6.4 collection combinations for `|`,
`in`, and infix `contains`.

Probe: `.temp/qa/fp16_explorer_probe.py` stressed empty unions, singleton-side
literal unions under Boolean logic, Quantity membership where an incompatible
candidate precedes a compatible equivalent, temporal precision mixtures, and
complex object collection equality.

Result: no new issue found. Native-loaded and forced fallback registrations
matched expected outputs, and the probe reported `FAILURES 0`.

Not a bug: complex objects with the same list-valued child items in different
order are distinct for Section 6.4 because union and membership use `=`
equality, not `~` equivalence.
