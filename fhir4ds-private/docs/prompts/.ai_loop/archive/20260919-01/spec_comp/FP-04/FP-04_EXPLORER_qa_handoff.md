# QA Handoff — FP-04 EXPLORER launch (3rd launch of FP-04 chunk)

**Personality**: EXPLORER (fuzzer/abuser)
**Chunk**: FHIRPath §5.2 Filtering and Projection — where(), select(), repeat(), ofType()
**Iteration**: 1 (min_iterations=1)
**Result**: 0 issues. 62 dual-path probes, all PASS with native↔fallback parity.

## What was probed

Probe script: `/mnt/d/fhir4ds/.temp/qa/fp04_explorer3_probe.py` (+ 15-case edge wave inline).

### 1. repeat() termination / self-reference
- `name.repeat($this)` identity projection — dedup terminates after round 1 (both paths).
- Constant projection `id.repeat('x')` → `['p1','x']` then stops.
- Ping-pong navigation `repeat(given | family | $this.given)` terminates via fixpoint dedup.
- `repeat(children())` on nested HumanName; self-similar `component.repeat(valueQuantity.value | component.valueQuantity.value)`; cross-round dedup with trailing union.
- Note: truly cyclic input objects are unreachable through the public SQL UDF boundary (JSON serialization), so termination correctness rests entirely on semantic-equality dedup — verified above.

### 2. select() multi-output and nesting
- Multi-output `select(family | given)`; nested `select(given.select(...))`; 3-level nesting; one-level flattening over mixed choice types (valueString | valueQuantity.value | valueBoolean); select on empty; select+where chain; `select($index)`.

### 3. where()/select() heterogeneous collections
- `contained.where($this.is(Observation))` over Observation/Condition/MedicationRequest mix.
- Empty criteria forms: `where({})`, `where(extension)`, `where(collapsing-to-empty)` — all → empty (spec: empty criteria treated as false).
- Non-boolean criteria (`where(family)`) — both paths agree (empty), treated as false.

### 4. ofType() unusual type names
- Unqualified `Quantity` vs `FHIR.Quantity` vs `System.String` on FHIR data; case variants `string`/`String`/`FHIR.string`; nonexistent `Collections` and `BogusType` → empty (fallback logs "Unknown type", native empty — parity at the UDF boundary); supertypes `DomainResource`/`Resource` (matches descendants); choice-typed `component.ofType(boolean)` / `ofType(Quantity)`; `status.ofType(code)`.

### 5. defineVariable / $index under nesting
- Variables referenced via `%name` (codebase convention, matches `test_filter_projection_parity.py`). Verified defineVariable evaluates at its definition context (`name.defineVariable('f', family).select(%f)` → both families per item — consistent); `where(%f = 'Chalmers')` → empty is correct (2-element collection ≠ singleton per §6.1 equality).
- `$index` in where (`name.where($index = 1).family` → `['B']`), in nested select (resets per inner collection), restoration after select, `$index + 1`, `iif($index = 0, ...)`.

### 6. Combinations
- where→select→repeat chains; repeat with ofType inside; select(ofType()); where inside repeat projection; `descendants().ofType(string).count()`; `Bundle.entry.resource.ofType(...)`, `repeat(resource.ofType(Resource).ofType(DomainResource))`.

## Non-issues verified (INTENDED / out-of-scope)
- `sum()`/`max()` → empty: documented FP-02 QA-001 decision (not FHIRPath N1/R4 functions).
- `%` operator not FHIRPath (`mod` is); `%` expressions return empty on both paths (lenient parse, parity holds).
- `$f`-style variable references rejected by pattern validator on both surfaces; `%f` is the supported form.

## Verdict
No CRITICAL/HIGH/MEDIUM/LOW issues. Clean exit eligible at iteration 1.
