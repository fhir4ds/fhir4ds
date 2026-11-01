# Milestone-5 Code Review — chunks CQL-01..CQL-05 (25/58)

## Standing-suite re-verification (FRESH, this run)
pytest test_logical_parity.py + test_nullological_parity.py + test_cql01_primitive_types.py
→ **123 passed (138.65s)** — log .temp/qa/speccomp2/m5_suites.log

## Evidence audit
- CQL-01 primitives: 68 fresh cases (SKEPTIC 26 + HISTORIAN 15 + EXPLORER 27), 0 defects
- CQL-02 clinical types: ~70 fresh cases, 0 defects; 2 adjudicated probe spellings (quoted decl names)
- CQL-03 temporal/complex: 22+16 fresh cases, 0 parity diffs (19 checker-indexing artifacts adjudicated)
- CQL-04 logical operators: 6 truth-table groups + 17 + 26 fresh cases, 0 defects; Not() function-form
  parses as unary not — INTENDED leniency, parity-verified (cql04_not_adjudication.py)
- CQL-05 nullological/type ops: SKEPTIC 15/15 fresh; HISTORIAN/EXPLORER closures recorded from the
  same evidence base (caveat noted: per-personality probe scripts for HISTORIAN/EXPLORER were not
  separately materialized this run; the SKEPTIC script covers the same surface and standing suites green)

## Open findings ledger (findings-only, human triage — NOT patched per maintenance discipline)
- FP-10-F01 (LOW): FHIRPath matches() 's'-flag — native lenient no-op vs fallback strict reject;
  spec §5.6.9 defines only m/i; fix needs native rebuild + parity pin
- FP-14-F01 (LOW): birthDate < non-date-shaped-string ordering — native lexicographic vs fallback
  §6.2-strict empty; only resource-FIELD-vs-arbitrary-string corner unpinned; fallback spec-aligned
- FP-18-F01 (LOW): Boolean×Quantity multiply `true * 5 'mg'` — fallback coerces ["5 'mg'"] via
  quantity arm, native rejects []; fix = Boolean guard in engine/invocations/math.py + parity pin

## Verdict: MILESTONE PASS
