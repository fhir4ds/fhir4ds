# Deep Research Findings: CQL-09 HISTORIAN

## Trigger

The first remediation pass fixed the focused CQL-09 comparison probes but the full conformance gate regressed DQM CMS2 from 47/47 to 46/47. CMS2 failed seven Numerator patients in both native-loaded and forced Python fallback DQM runs.

## Evidence

- `USE_CPP_EXTENSIONS=0` reproduced the CMS2 failure, so the regression is not solely caused by the rebuilt native CQL extension binary.
- The generated CMS2 SQL does not call `quantityCompare`/`quantity_compare`; the failure path is dominated by `intervalOverlaps`, `intervalContains`, `intervalStart`, `intervalEnd`, and `dateAddQuantity` around follow-up intervention timing.
- The CQL-09 comparison bug came from `_compare_at_min_precision` promoting a full Date operand to midnight DateTime for all callers. That made the official `DateTimeBetweenIsNull` case false instead of null.
- Interval UDFs also call `_compare_at_min_precision` through `_precision_aware_compare`. These interval helpers historically relied on Date/DateTime boundary promotion for measure-facing interval overlap/containment SQL, particularly day-bounded clinical windows.

## Root Cause

The first fix changed a shared temporal comparison primitive from permissive Date-to-DateTime promotion to strict precision uncertainty globally. That is correct for public CQL comparison operators (`between`, `<=`, `>=`, equality), but too broad for interval boundary helper internals where existing DQM SQL expects endpoint normalization behavior.

## Remediation Plan

Split the shared helper behavior:

- Keep `_compare_at_min_precision(..., promote_date_to_datetime=False)` strict by default for public CQL comparison helpers.
- Let interval boundary comparisons call `_compare_at_min_precision(..., promote_date_to_datetime=True)` so interval UDFs keep their day-boundary behavior.
- Add focused parity tests that cover both sides: direct comparison remains null for the official imprecise `between` case, while interval overlap/containment day-boundary behavior remains true across native-loaded and forced Python fallback registrations.

### Deep Research: QA-001

**1. Spec Determination:**
CQL Reference v1.5.3 Appendix B says integer and decimal comparisons use standard ordinal semantics, and List Operators such as Contains/Distinct/Except/Intersect use equality semantics for element comparison. List equivalence requires same-length lists with corresponding equivalent elements. Therefore adjacent exact Long/Decimal values must not become equal or equivalent because a SQL implementation rounds them to the same IEEE-754 binary value.

**2. Prior Art:**
Current CQL-18 durable findings already require list helper macros instead of DuckDB built-ins because DuckDB equality/null semantics diverge from CQL. The same helper layer is the correct place for direct public list helper parity, but literal-list equivalence currently bypasses it by decomposing `{...} ~ {...}` into per-element scalar equivalence.

**3. Approaches Attempted:**
First remediation replaced the mixed numeric branch in `CQLListElementEqual` from `DOUBLE` comparison to `DECIMAL(38,8)`. This fixed direct membership/equality helper reproducers, but the focused pytest still failed for translated `{ 9223372036854775807L } ~ { 9223372036854775806.0 }` because `_translate_list_equivalence()` expands literal-list equivalence into scalar `~` comparisons. That scalar decimal-literal equivalence path also emitted arithmetic over uncast numeric literals, allowing DuckDB to use an imprecise floating path.

**4. Blast Radius:**
Affected surfaces are CQL List Part 1 translated literal-list equivalence, and any scalar Long/Decimal equivalence expression that reaches `_translate_decimal_literal_equivalence`. Direct list helper macros are already fixed by the first change. Existing string, Quantity, tuple, interval, and dynamic list-helper paths should remain unchanged.

**5. Recommended Path:**
Keep the `CQLListElementEqual` `DECIMAL(38,8)` fix. Also cast operands inside `_translate_decimal_literal_equivalence()` to `DECIMAL(38,8)` before precision rounding so least-precision numeric equivalence uses exact CQL representational values rather than DuckDB floating arithmetic. Add a scalar translated equivalence regression alongside the list equivalence case.
