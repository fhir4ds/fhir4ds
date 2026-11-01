# Architect Handoff — CQL-06 closeout (iteration 1, resumed launch)

Date: 2026-08-20. Audit scope: the 3 landed fixes from the FIX phase,
spec-correctness, and regression risk against the conformance gate.

## Audit outcome

### QA-001 (HIGH) `.value` FHIR-primitive accessor — SOUND
- `_strip_primitive_value_segments()` in
  `fhir4ds/cql/translator/expressions/_property.py` is data-driven from
  `fhir4ds/fhirpath/models/r4/path2Type.json` (verified: `Patient.birthDate`
  → `date`, `Observation.status` → `code`, `Observation.valueQuantity` →
  `Quantity`, and the choice-type prefix `Observation.value` is a metadata
  MISS → segment kept, conservative). Guards skip paths with calls, quotes,
  or indexing. The `as`-unwrap identity for
  `(X as FHIR.<primitive>).value` correctly strips the model qualifier
  before the primitive check. No resource-type hardcoding; metadata misses
  fall through to prior behavior. Spec-correct per CQL 1.5 §09-b
  FHIRHelpers pattern (295 `.value` uses in bundled FHIRHelpers.cql).
- Load-bearing risk verified empirically: DQM 47/47 and FHIRPath 935/935
  hold with the rule in place — no measurable regression surface.

### QA-002 (MEDIUM) ConvertsToDecimal — SOUND
- `_DECIMAL_STRING_RE` now matches `(+|-)?#0(.0#)?`; representability gate
  `_fits_duckdb_decimal_rounded` makes integer-digit extent (DECIMAL(38,8))
  the only hard limit and lets excess scale round exactly like ToDecimal —
  internally consistent with CQL-01 doctrine. Dual-backend regression test
  green.

### QA-003 (MEDIUM) ConvertsToTime/ToTime timezone — DEFECT FOUND, REMEDIATED
- The FIX-phase change (reject timezone-suffixed Time strings) broke three
  OFFICIAL cql-tests fixtures (CqlTypeOperatorsTest ToTime2/3/4 expect
  `ToTime('T14:30:00.0+05:30')` → `@T14:30:00.000`): gate fell to 1703/1706.
  Per GLOBAL_RULES, official fixtures outrank spec prose in both directions.
- Remediated during closeout (allowed: verification exposed an actual defect
  in the landed fix): `_TIME_RE` regained a validated optional tz group;
  `ToTime` accepts and normalizes the marker away (invalid offsets like
  `+99:00` still rejected). QA-003 reclassified **INTENDED** — the observed
  offset acceptance is fixture-mandated behavior, not a spec violation.
  Regression test updated to enshrine fixture semantics.
- Re-verification: test file 11/11; master gate 2832/2832.

## Golden-standard invariants applied (scoped)
1. FHIR model knowledge must be data-driven (path2Type.json), never
   hardcoded resource branches — QA-001 fix complies.
2. ConvertsToX must mirror the ToX acceptance semantics — QA-002 complies;
   QA-003 now complies against fixture-defined semantics.
3. Official fixtures outrank spec prose and engine parity (GLOBAL_RULES) —
   enforced via the gate, which caught the QA-003 over-strict fix.

## QA audit (EXPLORER launch 3)
Thorough: dual-backend probing, round-trip batteries, precision ladders,
boundary offsets, retrieve-integrated checks. One spec-prose-vs-fixture
misjudgment (QA-003) — no retry needed since the gate caught it and the
reclassification is terminal. RETRY_QA: false.

## Handoff compression
QA (EXPLORER) probed CQL-06 conversion checks exhaustively on both backends
and filed 3 issues; the engineer fixed all 3 at root cause with regression
tests; the architect confirmed 2 fixes sound, caught the third over-reaching
spec prose against official fixtures, remediated, and re-verified the full
gate. Residual observations (not filed, out of chunk): Tuple-return column
projection yields resource references; ConvertsToQuantity still hard-rejects
>8 fractional digits (same class as QA-002, future chunk).

## Recommended fix order (future)
1. ConvertsToQuantity/ToQuantity >8 fractional-digit rejection (QA-002 class).
2. Tuple `{...}` return-column projection (needs a dedicated QA probe).
