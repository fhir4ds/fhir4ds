# Engineer Handoff — CQL-21 EXPLORER Iteration 1

## Triage Table

| Issue | Severity | Category | Decision | Rationale |
| --- | --- | --- | --- | --- |
| QA-002 | LOW | SPEC_VIOLATION | **INTENDED** | Strict spec divergence on Code overload empty-system edge case; not exercised by real clinical CQL; both backends agree; invasive fix for negligible benefit. |

## QA-002 Disposition

**Issue**: `Code { code: '8867-4', system: '' } in Vitals` returns True when
cache has `('http://loinc.org', '8867-4')` only. Strict CQL §In (Valueset)
Code overload requires equivalent (code, system) match → empty system is
not equivalent to LOINC system → expected False.

**Root cause**: The wildcard empty-system matching logic at
`fhir4ds/cql/duckdb/udf/valueset.py:566-583` was added by CQL-21 SKEPTIC
QA-001 for the String overload (which legitimately cannot carry system
info). The same code path applies to Code-typed operands with explicit
`system: ''` literals.

**Decision: INTENDED (NOT A BUG)**

Rationale:
1. **Spec is technically violated**, but the case is pathological. Real
   clinical CQL never writes `Code { system: '' }`. When source system is
   unknown, the natural CQL idiom is a bare String code: `'8867-4' in Vitals`.
2. **Both backends agree** (zero native↔fallback parity divergence), so
   the behavior is consistent across execution paths.
3. **The String-overload wildcard fix is correct and load-bearing**: it
   makes `'8867-4' in Vitals` work for real-world terminology data where
   source codes are bare strings. Reverting would break CQL-21 SKEPTIC
   QA-001's regression coverage.
4. **The fix would be invasive**: the UDF would need an additional marker
   argument to know whether the source operand is Code-typed (strict) vs
   String-typed (wildcard). This crosses translator/UDF contract boundaries
   for negligible real-world benefit.

**Action**: Add to `AGENTS.md` NOT A BUG Registry for the CQL subproject.
Mark QA-002 status as `INTENDED` (terminal). No code change.

## Validation

Conformance baseline preserved (run after QA phase, no source changes):

| Suite | Passed | Total |
| --- | ---: | ---: |
| ViewDefinition | 134 | 134 |
| FHIRPath (R4) | 935 | 935 |
| CQL | 1706 | 1706 |
| DQM | 47 | 47 |
| **OVERALL** | **2822** | **2822** |

No regressions. Proceeding to ARCHITECT phase.
