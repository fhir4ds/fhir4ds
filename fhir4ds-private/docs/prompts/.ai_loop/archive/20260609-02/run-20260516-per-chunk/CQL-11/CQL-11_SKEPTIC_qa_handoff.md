# QA Handoff - CQL-11 SKEPTIC

Scope: Arithmetic Operators Part 2 — Maximum, Minimum, Modulo, Multiply, Negate, Precision, Predecessor, Power, Round, Subtract, Successor, Truncate, and TruncatedDivide.

I performed a fresh SKEPTIC pass against the public DuckDB CQL arithmetic surface without relying on previous workflow output. The probe compared native-loaded registration, forced Python fallback registration, translated CQL execution, and raw C++/browser-style direct surfaces where macros or UDFs are available.

Findings logged: five real issues. Direct `mathRound` used the wrong negative tie behavior; SQL macro `Power` leaked `-nan`; compatible-unit Quantity modulo/truncated divide diverged between Python and C++; predecessor/successor boundary helpers returned out-of-range values or threw; and maximum/minimum DateTime/Time constants lost CQL lexical precision.

Post-fix verification reran the focused parity tests, native C++ CQL SQL tests, official CQL conformance, full conformance, and the full `fhir4ds` pytest suite.
