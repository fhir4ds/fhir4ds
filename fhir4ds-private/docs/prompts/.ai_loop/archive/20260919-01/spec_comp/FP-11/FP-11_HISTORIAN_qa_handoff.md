# QA Handoff — FP-11 §5.7 Math (HISTORIAN), iteration 1

Fresh dual-path (native extension vs forced Python fallback) audit on angles
orthogonal to the SKEPTIC pass, plus the direct-helper API surface. Probe:
`/mnt/d/fhir4ds/.temp/qa/fp11_historian2_2026_08_17/probe.py` (+ inline helper
probe), run with `PYTHONPATH=/mnt/d/fhir4ds`.

## Engine parity: 81 fresh cases, 1 diff (documented)

Fresh angles: SKEPTIC-fix re-verification on new variants (3.power(4), 2.power(62),
(-2).power(-3), 1.25.power(2), 10.power(-2)); abs/ceiling/floor/truncate typing
and edges ((-0.0).abs(), (-0.5).ceiling(), (-0.9).truncate(), int32 abs bounds);
Quantity operands for all §5.7 unary math (2.5 'mg'.ceiling/floor/truncate);
wrong-type inputs; round precision corners; log/ln/exp/sqrt domains
(1.log(1), 5.log(0.5), 5.log(-2)); iteration chaining (nums.select($this.abs()),
where($this.abs() = 4), multi.select(v.power(2)), all()); resource-field-driven
math (valueQuantity.value.power(2)); multi-item singleton errors; power extremes.

Only diff: `(0.001).power(1.37)` — the already-pinned <=1 ULP std::pow-vs-libm
drift (FP-11 SKEPTIC QA-006 LOW INTENDED). All 4 SKEPTIC fixes verified intact
and regression-free on both engines.

## Finding: QA-001 MEDIUM — direct helpers missed all 4 SKEPTIC fixes

`fhir4ds/fhirpath/duckdb/functions/math.py` (7th instance of the
exported-helper-API-forgotten family, predicted from institutional memory):
- `power(2,3)` → `[8.0]` Decimal vs engine Integer `8` (§5.7 Integer typing)
- `power(2,-3)` → `[0.125]` vs engine empty (negative Integer exponent, STU3)
- `power(1.1,2)` → `[1.2100000000000002]` binary64 noise vs engine `1.21`
- `round_fn(-0.4)` → `[-0.0]` vs engine `0.0`

Clean helper surfaces re-verified: abs/ceiling/floor/sqrt/exp/ln/trunc/log
values and domains; all log base guards; exp overflow; wrong-type/empty args.

QA-002 LOW INTENDED: transcendental ULP drift re-pin (above).
