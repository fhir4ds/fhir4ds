# QA Handoff — FP-05 SKEPTIC, iteration 1 (2026-08-17)

**Chunk**: FHIRPath §5.3 Subsetting + §5.4 Combining.
**Personality**: SKEPTIC (hypothesis attacker).
**Spec source**: FHIRPath N1 §5.3/§5.4 normative text (fetched from hl7.org/fhirpath/N1/).

## What was probed

Dual-path probes (native C++ extension connection with
`allow_unsigned_extensions=True` vs forced Python-fallback connection, both via
`SELECT fhirpath(?, ?)`) in `/mnt/d/fhir4ds/.temp/qa/fp05_skeptic_2026_08_17/`
(probe.py 67 cases, probe2.py 38 cases, probe3.py is_valid + strict-core battery):

- Indexer `[i]`: 0-based, out-of-range -> empty, negative -> empty, empty input
  -> empty, non-Integer index -> execution error -> UDF empty, expression-valued
  index, INT32_MAX index. Correct in both engines.
- `single()`: 1 item -> item, 0 items -> empty (NOT error, matches N1), 2+ ->
  evaluation error -> UDF empty. Correct.
- `first()/last()/tail()`: empty/single/multi, on data fields, chained. Correct.
- `skip(num)`: normal, == size, oversized, 0 -> input returned, negative ->
  input returned, empty input, non-Integer args -> error->empty, INT32_MAX,
  expression-valued num. Correct.
- `take(num)`: normal, oversized -> fewer, 0/negative -> empty, non-Integer
  args -> error->empty. Correct.
- `intersect`/`exclude`: `=`-equality membership (1 = 1.0 dedup/exclusion;
  1 'cm' = 10 'mm'; offset-temperature empty-equality members count as
  non-members), intersect dedups, exclude keeps duplicates and order (verified
  with combine-built duplicate collections since `|` dedups at construction),
  empty corners, self-intersect, resource/object members. Correct.
- `union`/`combine`: union dedups via `=` incl. quantity/1.0-vs-1 cases and
  empty operands; combine preserves duplicates and never dedups (1.combine(1)
  -> [1,1]; 1.combine(1 '1') -> 2 items), empty corners. Correct.
- Strict core engine (`fhir4ds.fhirpath.evaluate`): single() error/empty forms,
  skip(-1)/take(-1)/[-1] confirmed.

**Parity diffs: 0 across all probes.** §5.3/§5.4 evaluation semantics are
spec-compliant and engine-parallel; the 2026-05-16 FP-05 fixes hold.

## Issues found

- **QA-001 (MEDIUM, OPEN)**: `fhirpath_is_valid` returns False for
  statically-known wrong-typed §5.3 arguments (`(1|2|3).skip('x')`,
  `.take(true)`, `[1.5]`, `'abc'['x']`) on BOTH surfaces, while the same
  execution-type-error class is accepted elsewhere (`'a' - 'b'` -> True,
  unary +/-, Boolean ordering). Root cause: those error message forms were
  never added to the accepted lists in `udf.py::_is_valid_empty_result_error`
  and native `FhirpathIsValidFunction`. Singleton/multi-item violations stay
  invalid (doctrine preserved). See evolution.json.

## Environment note

Native-extension probe connections require
`duckdb.connect(config={"allow_unsigned_extensions": True})`; without it
registration silently falls back to Python UDFs and a "native" probe is
actually double-fallback (first probe run initially hit this).
