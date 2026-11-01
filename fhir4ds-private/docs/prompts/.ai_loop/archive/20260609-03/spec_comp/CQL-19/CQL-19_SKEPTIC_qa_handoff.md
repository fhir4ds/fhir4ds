# QA Handoff - CQL-19 SKEPTIC

## Scope

CQL List Operators Part 2: Last, Length, list inequality/equivalence negation, properly includes/included in, singleton from, Skip, Tail, Take, and Union.

## Spec Anchor

Verified against the current CQL Reference v1.5.3 Appendix B List Operators (`https://cql.hl7.org/09-b-cqlreference.html#list-operators`) and the bundled official `CqlListOperatorsTest.xml`.

## Hypotheses Probed

1. Direct list `Length` may inherit string macro null behavior instead of list null-to-zero semantics.
2. `Skip` / `Take` count arguments may be implicitly coerced by DuckDB instead of enforcing the CQL `Integer` signature.
3. `singleton from` over runtime-produced lists may return null instead of raising for multi-item lists.
4. `properly includes` / `properly included in` may bypass CQL list equality for Quantity, null, or temporal values.
5. `union` may deduplicate through raw DuckDB equality instead of CQL element equality for Quantity, clinical, and null elements.

## Findings

### QA-001 HIGH - Direct Length over typed null lists returned null

Fresh probe `.temp/qa/cql19_skeptic_probe.py` showed `SELECT Length(NULL::INTEGER[])` returned SQL `NULL` across forced Python fallback, native-loaded registration, and no-Python C++ macro registration. The list operator surface must return `0` for a null list, consistent with the official `Length(null as List<Any>)` XML case.

### QA-002 HIGH - Skip/Take accepted non-Integer counts

Fresh probe showed direct `Skip([1,2,3], 1.5)` returned `[3]`, direct `Take([1,2,3], 1.5)` returned `[1,2]`, and direct `Take([1,2,3], '1')` returned `[1]` across all three registrations. Translated `Skip({1,2,3}, 1.5)` and `Take({1,2,3}, 1.5)` were accepted. The CQL Reference signatures require `number Integer` for both operators.

## Validation Run

Initial fresh probe failed with the two findings above. No source code was modified during QA discovery.
