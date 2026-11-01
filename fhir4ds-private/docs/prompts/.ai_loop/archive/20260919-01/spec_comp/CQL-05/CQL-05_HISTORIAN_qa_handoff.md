# QA Handoff — CQL-05 Structural Type Operators (HISTORIAN, iteration 1)

## Personality / scope
HISTORIAN: used prior-launch memory (spec_comp/CQL-05 SKEPTIC handoffs) to target what the
SKEPTIC pass may have missed, re-verified its 4 fixes for regression, and hunted NEW
divergences beyond the original probes. Chunk: As<T>, Children, Convert to<T>, Descendants, Is<T>.

## Spec verification (cql.hl7.org/09-b-cqlreference.html, fetched this launch)
- ToBoolean accepts true/t/yes/y/1 and false/f/no/n/0 (case-insensitive), else null →
  `convert 'yes'/'y'/'1' to Boolean` → True/True/True is SPEC-CORRECT (initially suspected, cleared).
- ToInteger accepts Boolean (true→1) → `convert true to Integer` → 1 correct.
- ToString(Quantity) format `(-)?#0.0# (('<unit>')|(<unit>))` → "1 'mg'" correct.
- Children/Descendants over list arguments: "invoke on each element ... and flatten the
  resulting lists"; list-valued elements expanded individually.
- Is: run-time type test, same-or-derived; `null is T` false. As: null on mismatch.

## Re-verification of SKEPTIC fixes (all regression-free)
- First/Last/singleton-from over bare retrieves ✓ (First([Observation]) works, correlated subquery).
- Children()/Descendants() query-source aliases UNNEST per element: `exists ([Observation] O return
  Descendants(O) D where D is FHIR.Quantity)` → True ✓; `Children(O) C where C is FHIR.code` → True ✓;
  `Children(O) C where C is Observation` → True ✓. py/cpp parity held.
- FHIR string-family `is String`: `O.status is String` → True ✓; `O.value is String` over choice → True ✓;
  `O.value is FHIR.string` → True ✓.
- List-literal aliased sources: `({1,2} N where ...)` ✓.
- Convert matrix (17 literal probes + retrieve-backed convert) all spec-correct with py/cpp parity.
- As/Is literal semantics (null-as, mismatch-as-null, null-is-false, FHIR/System qualifiers) ✓.

## NEW issues
- QA-101 (HIGH): Query aliases bound to `as`-cast expression sources discard the cast. The alias is
  silently bound to the enclosing retrieve rows; is/null checks then evaluate against the whole
  resource JSON. `Count([Observation] O return O.value as FHIR.Quantity Q where Q is FHIR.Quantity)`
  → 0 (expected 1); `Q is not null` → 2 (expected 1, As must null the valueString row); even
  `'x' as String X where X is String` → 0. Silent wrong results on both native and Python paths —
  pure SQL-generation bug (`_alias_is_element_value` in _query.py recognizes list literals and
  Children/Descendants sources but not As-expression sources). Valid CQL 1.5: a query source may be
  any expression with an alias; the alias binds to each element.
- QA-102 (MEDIUM): `Descendants({1, {2, 3}})` → DuckDB Binder Error ("Cannot deduce template type
  'T'"). Spec requires flattening: expected [2, 3]. Nested list literals inside list-literal
  arguments fail to serialize/exec; tuples containing lists and flat lists are fine.

## Verified-clean surfaces (no action)
Children/Descendants over primitives ([]), null propagation for all five operators, empty-list
behavior, Descendants of tuple-nested-tuple document order, Is subtyping rules (Integer not
Long/Decimal), FHIR-qualified Is on choice values, convert Date/Time/DateTime/Long/Quantity,
cast-vs-As strictness (unchanged from SKEPTIC), native/Python parity on every probe.

Reproducers: /mnt/d/fhir4ds/.temp/qa/cql05_probe{,2..9}.py
