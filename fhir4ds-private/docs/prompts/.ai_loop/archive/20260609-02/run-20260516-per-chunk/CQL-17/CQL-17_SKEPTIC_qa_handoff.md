# QA Handoff - CQL-17 SKEPTIC

Spec source: CQL v1.5.3 Appendix B, Interval Operators, including Point From, Properly Includes/In, Same As, Same Or After/Before, Size, Start, Starts, Union, and Width.

Fresh probe: `.temp/qa/cql17_skeptic_probe.py`

Hypotheses tested:
- Open-bound unit intervals are likely mishandled because Python fallback normalizes open bounds but some public helpers still return raw JSON bounds, while C++ helpers may require authored closed endpoints.
- Interval `same <precision> as` may compare interval JSON as a single temporal value rather than comparing semantic starts and ends separately.
- Precision interval predicates over partial Date/DateTime values may truncate strings instead of preserving CQL uncertainty.
- Interval union/size/width and properly-includes paths may diverge across forced Python fallback, native-loaded registration, and no-Python/browser-style C++.

Findings:
- `QA-001` HIGH: `pointFrom` and no-Python C++ `intervalWidth` diverge or violate open-bound effective semantics for integer intervals. Examples: `point from Interval(4, 5]` should return `5`; forced Python/native-loaded returned `4`, no-Python C++ returned NULL. `point from Interval[4, 5)` should return `4`; no-Python C++ returned NULL. `width of Interval(4, 9]` should return `4`; no-Python C++ returned `5`.
- `QA-002` HIGH: translated interval `same day as` returns true when starts match but ends differ. SQL routes whole interval JSON values into `cqlSameAsP(...)` instead of comparing `intervalStart` and `intervalEnd`.
- `QA-003` MEDIUM: translated `starts day of` over partial dates returns false instead of NULL when the relationship is uncertain.
- `QA-004` MEDIUM: translated `properly includes day of` and `properly included in day of` over partial dates return false instead of NULL and route through non-precision helpers.

Baseline check before remediation:
- Existing focused CQL-17 parity pytest passed: `3 passed`.
- Fresh SKEPTIC probe failed with the findings above.
