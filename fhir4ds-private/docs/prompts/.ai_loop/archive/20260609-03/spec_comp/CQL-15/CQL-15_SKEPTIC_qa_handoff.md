# QA Handoff: CQL-15 SKEPTIC

Scope: SPEC COMPLIANCE CHUNK CQL-15, Interval Operators Part 1, personality SKEPTIC. `docs/architecture/translator/AGENTS.md` was requested but is absent; root `AGENTS.md`, `extensions/cql/AGENTS.md`, loop rules, state schema, and durable knowledge were used instead.

Findings:
- `QA-001` HIGH: `expand { Interval[1 'g', 3 'g'] } per 1 'g'` failed to parse the UCUM unit and Quantity interval expansion diverged across Python fallback/native/no-Python surfaces.
- `QA-002` HIGH: Quantity interval semantic boundaries were wrong for `end of Interval[1 'g', 2 'g')` and `Interval[1 'g', 2 'g'] except Interval[1500 'mg', 2 'g']`.
- `QA-003` HIGH: Python/native `intervalContains(Interval<Quantity>, scalar)` coerced bare scalar points to numeric values while no-Python C++ returned NULL.

Fresh QA probe: `.temp/qa/cql15_skeptic_probe.py` attacked open/closed boundaries, unbounded intervals, partial precision, Quantity compatibility, scalar-vs-Quantity containment, `except`, `collapse`, and `expand` across forced Python fallback, native-loaded registration, and no-Python/browser-style C++.
