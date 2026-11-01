# Engineer Handoff — FP-01 SKEPTIC Iteration 1 FIX (2026-08-16)

## Scope
All 7 QA issues (QA-001..QA-007) from the SKEPTIC iteration-1 QA phase, plus one
new issue discovered during validation (QA-008). Session resumed from an
interrupted FIX whose partial edits (quoted-keyword canonicalization sketch,
cross-group compare sketch, QA-007 mask, parity tests) were verified, corrected,
and completed rather than redone blindly.

## Triage table
| ID | Sev | Category | Terminal | One-line outcome |
|---|---|---|---|---|
| QA-001 | HIGH | SPEC_VIOLATION | RESOLVED | Quoted calendar keyword units canonicalized to bare form at `FP_Quantity` construction |
| QA-002 | HIGH | SPEC_VIOLATION | RESOLVED | Same fix; quoted plurals now valid in date/time arithmetic (parity with native) |
| QA-003 | MEDIUM | SPEC_VIOLATION | RESOLVED | §5.5.7 factors (1 month = 30 d, 1 year = 365 d) applied to unanchored equality in BOTH engines |
| QA-004 | MEDIUM | PARITY_DIVERGENCE | RESOLVED | Cross-group ordering uses the same factors in both engines (spec semantics, not just parity) |
| QA-005 | LOW | PARITY_DIVERGENCE | RESOLVED | Direction corrected via official R4 test: native now normalizes `-0.0` → `0.0` (Python was right) |
| QA-006 | LOW | PARITY_DIVERGENCE | RESOLVED | Display parity via QA-001 canonicalization (`4 'year'` → `4 year`) |
| QA-007 | LOW | PARITY_DIVERGENCE | RESOLVED | Python fallback `fhirpath_json` quantity values use precision-15 mask like native |
| QA-008 | MEDIUM | SPEC_VIOLATION (harness) | RESOLVED | Conformance harness adapter emitted dangling AND; generator SQL was correct; harness fixed, ViewDef 144/144 |

## Key design decision (QA-003/QA-004)
The N1 §5.5.7 factor table is month-based for year↔month (`1 year = 12 months`)
and day-based for year/month-vs-day-and-below (`1 month = 30 days`,
`1 year = 365 days`); no single seconds-per-unit mapping satisfies all rows
(12 × 30 d = 360 d ≠ 365 d). Therefore:
- year↔month pairs (calendar or UCUM) compare in **months** (12/1) — preserves
  `1 year = 12 months`, `1 'a' = 12 'mo'`.
- cross-group pairs convert the calendar keyword operand with **explicit
  2592000 s / 31536000 s**; all other units use the UCUM table unchanged.
- UCUM `'mo'`/`'a'` keep mean-duration seconds (2629746/31556952): `1 'mo' = 29
  days` stays false, `1 'mo' > 29 days` stays empty (§6.2), `1 month = 1 'mo'`
  stays empty (§6.1.1).
- `extensions/fhirpath/src/include/shared/ucum_units.hpp` is **byte-identical**;
  the CQL extension was not rebuilt; CQL conformance held at 1706/1706.
  Comparison factors live only in the comparison sites, so toQuantity
  (`(1 year).toQuantity('month')` → `12 month`) and quantity arithmetic/division
  are untouched in both engines.

## Files changed (working tree, uncommitted)
Python engine:
- `fhir4ds/fhirpath/engine/nodes.py` — canonicalization in `__init__`;
  `_year_month_ucum_units`; `_calendar_unanchored_seconds_factor` +
  `_unanchored_duration_seconds`; `__eq__`/`deep_equal` cross-group branches;
  `compare()` guard relaxation + factor-based cross-group branch.
- `fhir4ds/fhirpath/engine/invocations/equality.py` — `_quantity_base` routes
  duration units through the helper; year↔month months-branch in `equality()`.
- `fhir4ds/fhirpath/engine/evaluators/__init__.py` — comment documenting that
  Decimal unary-minus zero normalization is official-test-correct (behavior
  unchanged).
Native (rebuilt + deployed to `fhir4ds/fhirpath/duckdb/extensions/`):
- `extensions/fhirpath/src/fhirpath/evaluator.cpp` — `yearMonthMonthsFactor` +
  `unanchoredDurationSeconds` helpers; `quantityEqualState`,
  `quantityEquivalentState`, `quantityValuesEqual`, and the §6.2 ordering site
  now use months/factor semantics; `isMixedCalendarUcumDurationAboveSeconds`
  exception for calendar-YM vs UCUM-weeks/days/time; unary-minus negative-zero
  normalization (Decimal + Quantity branches).
Wrapper + harness:
- `fhir4ds/fhirpath/duckdb/udf.py` — `fhirpath_json` precision-15 mask (from
  interrupted session, verified).
- `conformance/scripts/run_viewdef.py` — `_add_resource_type_filter` rewritten
  to push the predicate into `FROM resources t` (QA-008).
Tests:
- `fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py` — 6 new
  parity tests (31 total in file), spec-correct expectations.

## Validation (PROC_VALIDATION)
- Focused: `test_literal_parity.py` 31/31; fhirpath duckdb suite 1394/1394;
  fhirpath unit 178/178; CQL tests 4866 passed/4 skipped.
- FHIRPath R4 conformance: 935/935 (the QA-005 misdirection briefly broke
  HighBoundaryDecimal16; reverted and fixed native instead).
- ViewDefinition conformance: 144/144 (was 143/144 at clean HEAD — QA-008).
- Final `run_all.py`: see `.temp/qa/fp01_skeptic_final_conformance.log`
  (CQL 1706/1706, DQM 47/47 verified mid-flight; final numbers in log).
- QA-008 pre-existence proven via temp git worktree at HEAD db1e4164
  (143/144 identical failure) — not a regression from this loop.

## First-fail event + recovery (for the record)
The first QA-005 fix attempt (preserve `-0.0` in Python via `copy_negate`)
failed validation: official R4 `HighBoundaryDecimal16`
(`-0.0034.highBoundary(1)`) expects `0.0`. Recovery per the diagnostic gate:
reproduced, root-caused via the official fixture, corrected the fix direction
(native normalizes, Python unchanged), rebuilt, revalidated. No blind second
attempt was made.

## Notes for Architect
- `PROC_VALIDATION.md` baseline table is stale: the committed ViewDefinition
  suite has 144 tests (10 added since 2026-04-24), total 2832. Recommend
  updating the baseline table and adding the harness-adapter lesson to
  GLOBAL_RULES (validate generated-SQL failures against raw generator SQL
  before blaming the generator).
- Native rebuild + deploy convention used: `cmake --build
  extensions/fhirpath/build/release -j 8` then copy
  `build/release/extension/fhirpath/fhirpath.duckdb_extension` to
  `fhir4ds/fhirpath/duckdb/extensions/`.
