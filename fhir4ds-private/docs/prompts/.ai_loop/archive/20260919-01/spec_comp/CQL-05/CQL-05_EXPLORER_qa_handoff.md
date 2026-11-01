# QA Handoff — CQL-05 EXPLORER (iteration 1, 2026-08-20)

Personality: EXPLORER (fuzzer/abuser). Chunk: CQL 1.5 structural type operators
(As<T>, Is<T>, Convert to<T>, Children, Descendants).

## What was probed

- Baseline gate re-run before probing: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).
- Is/As chains and nested casts: `as Any` round-trips, `as T is T`, List<T>/Tuple as-targets,
  Quantity unit preservation through double as-cast (`5 'mg'` string + equality) — all correct
  on both native and forced-python paths.
- Children/Descendants: deep tuple nesting (4 levels), lists of complexes, null-child preservation,
  temporal/Long transport inside descendants (`is Date`/`is Long` true), FHIR resources at depth
  (Sum of Descendants over retrieves = 42 across 4 observations), Children per-element union
  semantics consistent with FHIRPath children().
- Convert matrix: String↔Integer/Decimal/Boolean/Quantity/Date/DateTime/Time, Integer↔Decimal,
  Boolean→Integer, Integer/Quantity→String ('5.0 'mg''), DateTime→Date, round-trips, null operands,
  list operands, Code↔Concept conversions — all correct and native/python parity held everywhere.
- Choice-typed value[x]: `O.value is FHIR.Quantity/integer/string/boolean` counts all correct
  (1/1/1/1 on the fixture); `as FHIR.Quantity` in where clauses with parameter refs; `as FHIR.integer`
  then arithmetic (+10 → 17) — correct.
- Aggregate/where/retrieve combinations with structural ops, component.valueQuantity backbone chains.

## Issues found (logged in evolution.json)

- QA-104 HIGH: strict-cast `error()` CASE inside +,-,* arithmetic gets TRY()-wrapped because
  `_contains_function_call` does not recurse into SQLCase → DuckDB BinderException
  (invalid SQL) for valid CQL like `(cast 5 as Any) + 1`. Both backends.
- QA-105 HIGH: element access over define alias bound to bare retrieve is broken:
  `define L: [Observation]` then `First(L).id` / `L[1].status` / `Count(First(L).contained)`
  → null. Inline `First([Observation]).id` works.
- QA-106 MEDIUM: array/backbone property access (`.contained`, `.component`) on singleton
  results (`First([Observation])`, `singleton from [Observation]`) returns 0/null;
  query-source access works. Children() shows the elements exist.

## NOT A BUG registry candidates (verified consistent across paths, spec-consistent)

- `Children({1,2,3})` → 0: Children applies per element (union of children of elements),
  matching FHIRPath children() semantics; scalars have no children.
- `convert '5 mg' to Quantity` → null: ToQuantity requires quantity-literal format with
  quoted unit (`'5 ''mg'''` works).
- `convert Code/Concept to String` → null: no ToString overload for Code/Concept in the
  CQL 1.5 conversion table.
- `is FHIR.ObservationStatus` → TranslationError "unknown type": enum/code-binding names are
  not FHIR ModelInfo types; clear failure is correct per no-silent-guessing rule.
- `convert true to Integer` → 1, `'yes' to Boolean` → true: already in registry.

Reproducers: /mnt/d/fhir4ds/.temp/qa/cql05_explorer2_2026_08_20/ (discovery.py,
isolate.py, first_alias_probe.py, contained2.py, arrayprop.py).
