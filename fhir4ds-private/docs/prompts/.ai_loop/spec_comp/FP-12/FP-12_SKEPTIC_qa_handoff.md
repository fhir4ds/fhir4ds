# QA Handoff — FP-12 SKEPTIC (§5.8/§5.9 Tree Navigation + Utility)

## Verdict: CLEAN — zero defects (22 + adjudication-matrix cases; 3 MISS adjudicated)

children()/descendants() semantics (values included, resourceType skipped, scalar→empty,
descendants superset + distinct); trace passthrough + with-projection + in-where;
now/today/timeOfDay determinism (`now() = now()` true; today ['2026-10-02'] shape;
timeOfDay ['HH:MM:SS.mmm']; now ['YYYY-MM-DDTHH:MM:SS+00:00']); compositions.

## Adjudication (3 MISS → probe-expectation errors, spec-grounded)
`today().matches(pat)` / `now().matches` / `timeOfDay().matches` → [] on BOTH engines.
MECHANISM: matches()/length() take String input (§5.6.9/§5.6.11); Date/DateTime/Time →
String is §5.5 EXPLICIT-ONLY. Resource temporal FIELDS (birthDate — FHIR primitive
whose JSON form is the wire repr) ARE accepted (birthDate.matches('19') → true both —
the pinned JSON-convenience convention), but function/literal-produced SYSTEM temporal
values (today()/now()/@literals) are NOT (→ row-resilient empty, both engines
byte-identical). Correct spelling: `.toString().matches(...)`. type() reflection
confirms: birthDate.type().name=['date'] vs today().type().name=['Date'].
Zero parity diffs anywhere (9/9 adjudication matrix OK).

Evidence: .temp/qa/speccomp2/fp12_skeptic_probe1.py + inline adjudication matrices.
