# Architect Handoff — CQL-17 HISTORIAN (2nd launch) iteration 1 (2026-08-22)

## Iteration summary (compressed)

QA (HISTORIAN, institutional-memory-driven): 28 translated defines + 16
direct UDF probes × 3 engines; re-verified all 3 SKEPTIC fixes hold; found
4 NEW issues by applying the CQL-16 "probe MIXED POINT TYPES on interval
bounds" lesson. Engineer fixed all 4 at root cause: translator point-type
dispatch for the no-precision same/same-or interval family (2 HIGH),
native cross-type width/size (MEDIUM), canonical Quantity bound JSON
dual-engine lockstep (MEDIUM). Extension rebuilt + redeployed. Regression
coverage added (3 new parity tests, 30+ defines × 3 engines; 2 stale
expectations updated in part2/part3 suites).

## Structural audit (golden standard: .temp/architect/golden_standard.md)

- Translator fix uses static CQL AST typing (`_static_structural_type_name`
  + literal-bound peek) — same precedent as the SKEPTIC union dispatch fix;
  no layer crossing, no SQLRaw, no test-specific hardcoding; generalizes to
  Long/Decimal/Quantity/mixed literals and identifiers typed via
  Interval<X>. Temporal operands and unknown types keep the existing
  temporal lowering (no behavior change outside the bug class). CLEAN.
- Native width/size cross-type fallback is additive; exact uint64/__int128
  integer paths preserved; mirrors the CQL-16 BoundValue::compare precedent.
  CLEAN.
- Quantity canonicalization achieves byte-identical JSON across engines
  (canonical key order value/unit/code/system, float value, UCUM system),
  routed through single helpers per engine. Dual-engine lockstep doctrine
  satisfied with 3-engine parity tests. CLEAN.
- No silent fallbacks added; one misrouting removed. No architecture drift.

## Follow-up finding (pre-existing, logged to AGENTS.md)

Native unittest `extensions/cql/test/sql/cql.test:110`
(`cqlDurationBetween('2012-01-02','2012','month')` → end 10 vs expected 11)
fails in the working tree WITH this launch's patch reverted — it predates
this launch (prior sessions' uncommitted native changes). Not covered by
the master gate. Needs a dedicated follow-up launch.

## QA enforcer gate

QA was rigorous: spec-anchored (fetched normative §19 text), three-engine
probing, prior-fix re-verification, and it mined institutional memory for
new attack surfaces rather than re-running old probes. All 4 findings
reproduced, root-caused, fixed, and regression-tested. No veto.

## Final validation (FINAL tree state)

Master gate `conformance/scripts/run_all.py`, fresh run after the last
code change (GATE DISCIPLINE): ViewDefinition 144/144, FHIRPath 935/935,
CQL 1706/1706, DQM 47/47 (no ERRORs; no REV-009 retry needed),
OVERALL 2832/2832 — baseline holds.
Focused: test_interval_part2_parity.py + part3 22/22;
interval+quantity UDF suites 126/126; interval_udfs + v2_expressions 204/204.
Extension binary md5 3e7d4167143e01907fdd8561db43b7d7, matched across repo
bundle (fhir4ds/cql/duckdb/extensions/cql.duckdb_extension) and site-packages
(~/.local/lib/python3.10/site-packages/...).

## Exit

Iteration 1 ≥ min_iterations (1); zero non-terminal CRITICAL/HIGH/MEDIUM
issues (QA-001..004 RESOLVED/VERIFIED). Exit reason: CLEAN.
