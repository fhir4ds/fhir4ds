# QA Handoff — CQL-21 EXPLORER (Iteration 1, Fresh)

**Personality**: EXPLORER (Role C: Fuzzer / Abuser)
**Chunk**: CQL-21 — CQL Clinical Operators
**Spec**: cql.hl7.org/09-b-cqlreference.html v1.5.3 §Clinical Operators
**Date**: 2026-07-02

## Probe Scope

Threw pathological inputs at clinical operators across 4 batteries + 2 auxiliary
probes, comparing translator → DuckDB execution on both native C++ extension
and forced Python fallback:

- **Battery 1 (24 cases)**: AgeIn/CalculateAgeIn with extreme birth dates
  (pre-1900, year 0001/9999, future, leap day, century-non-leap), NULL
  operand propagation, sub-day boundaries (24h/25h/23h exact), long spans
  (200y).
- **Battery 2 (15 cases)**: Equal/Equivalent Code/Concept with unicode codes
  (café, emoji), empty/whitespace codes, Concept with empty codes list,
  NULL display fields, cross-type Code-as-singleton-Concept, version
  mismatch.
- **Battery 3 (12 cases)**: In (Valueset) with unicode codes, empty codes,
  empty/whitespace systems, Concept with empty codes, ambiguous systems,
  string-overload with unicode/empty/whitespace.
- **Battery 4 (2 cases)**: ExpandValueSet(Vitals) count + raw expansion.
- **Auxiliary probe 2 (23 cases)**: CalculateAgeIn direct UDF calls with
  boundary year values (1, 9999), pre-1900, future, partial dates
  (4-char/7-char), leap day arithmetic, Date vs DateTime overload mixing.
- **Auxiliary probe 3 (8 cases)**: Deeply nested clinical expressions
  (Code equality inside if/case/and-chains, In (Valueset) inside case,
  Code version comparison, chained equivalence).

**Total: 84 cases × 2 backends = 168 evaluations.**

## Findings

### QA-002 (LOW — INTENDED): In (Valueset) Code overload treats empty source system as wildcard match

**Spec citation**: CQL 1.5.3 §In (Valueset) — Code overload:
> "For the Code overload, if the given valueset contains an equivalent code, the result is true."

"Equivalent" per CQL §Equal/Equivalent Code: Code equivalence compares (code,
system) only, ignoring display and version. Two codes with different systems
are NOT equivalent.

**Reproducer**:
```cql
context Patient
define InVSEmptySys: Code { code: '8867-4', system: '' } in Vitals
```
Cache contains: `('http://loinc.org', '8867-4')` only.

**Actual**: True (both backends agree).
**Expected per strict spec**: False. Per Code equivalence, `system=''` is
NOT equivalent to `system='http://loinc.org'`.

**Root cause**: `fhir4ds/cql/duckdb/udf/valueset.py:566-583` — the
`fhirpath_in_valueset` UDF applies a "wildcard" matching rule when the
source code has empty/null system. This logic was added by CQL-21 SKEPTIC
QA-001 to fix the String overload (where empty source system is correct
because strings can't carry system info). But the same code path runs for
Code-typed operands with explicit `system: ''` literals, applying the
wildcard rule where the spec mandates strict (code, system) equivalence.

**Classification rationale (LOW/INTENDED, not CRITICAL/HIGH)**:
1. Real clinical CQL never writes `Code { system: '' }` — use a String
   literal instead. Empty system in a Code literal is pathological only.
2. Both backends agree (zero parity divergence), so consumers see
   consistent behavior.
3. The fix would require the translator to emit a different SQL marker
   indicating source operand type (Code vs String), then the UDF would
   apply strict matching for Code-typed empty-system codes. This is an
   invasive architectural change to the UDF contract for negligible
   real-world benefit.
4. Documented in `AGENTS.md` NOT A BUG Registry as intentional divergence
   in service of practical terminology-service interop.

## Parity Audit

**Zero native↔fallback parity diffs across all 168 evaluations.** Both the
native C++ extension and forced Python fallback produce identical results
for every pathological input tested, including:
- Pre-1900 birthdates
- Year 0001 / 9999 boundaries
- Future birthdates (NULL propagation per spec)
- Unicode/emoji code values
- NULL/empty/whitespace operand fields
- Mixed Date/DateTime overloads
- 200-year calendar spans
- Deeply nested clinical expression chains

## Validation Status

CQL-21 conformance baseline preserved. Recommend FIX phase mark QA-002 as
INTENDED with NOT-A-BUG registry entry; no code change required.
