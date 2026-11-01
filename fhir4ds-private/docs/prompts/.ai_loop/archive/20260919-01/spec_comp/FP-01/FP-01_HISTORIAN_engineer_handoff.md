# Engineer Handoff — FP-01 HISTORIAN Iteration 1 FIX (2026-08-16)

## Scope
3 issues: QA-001 (MEDIUM, mixed calendar-vs-UCUM year/month equality), QA-002
(LOW, Time-arithmetic result T-prefix rendering), QA-003 (LOW, new parity
divergence discovered while root-causing QA-002).

## Triage table
| ID | Sev | Category | Terminal | One-line outcome |
|---|---|---|---|---|
| QA-001 | MEDIUM | SPEC_VIOLATION (spec prose vs official fixture conflict) | INTENDED | Prose-literal fix implemented then REVERTED per Recovery Gate: official R4 fixtures pin `'1 'a''.toQuantity() = 1 year` (and 'mo' analog) to EMPTY; fixtures outrank prose (QA-005 precedent). Guard test added. |
| QA-002 | LOW | SPEC_VIOLATION | RESOLVED | Time-arithmetic results now render T-less (`15:04:28`) and remain Time values in BOTH engines (native string_val prefix dropped; Python returns FP_Time node). |
| QA-003 | LOW | PARITY_DIVERGENCE | RESOLVED | Fallback `datetime_equality` no longer coerces plain Strings against FP_Time peers (§5.5 Explicit-only); Time-vs-plain-String is empty in both engines. Date/DateTime-vs-string coercion (both-engine JSON convention) unchanged. |

## The QA-001 event (full record for the architect)
1. QA evidence: both engines returned empty for `1 year = 1 'a'`; N1 §6.1.1
   AND published v3.0.0/master §6.1.1 + §4.1.8 say false ("considered
   unequal", "1 year is not equal to 1 'a'"). Fix direction seemed clear.
2. Implemented false-semantics in both engines (Python equality.py +
   nodes.py guards; native quantityEqualState/valuesEqualState/operator
   lambda + outer block), rebuilt + redeployed, updated 4 stale SKEPTIC
   test expectations, added a new guard test.
3. **Recovery Gate fired**: FHIRPath R4 conformance dropped 933/935 — the
   two failures are `testStringQuantity{Month,Year}LiteralToQuantity`
   (`'1 'a''.toQuantity() = 1 year`), whose fixture entries carry NO
   `<output>` element = the harness's expected-EMPTY contract. The official
   suite directly contradicts the prose.
4. Reverted all QA-001 code in both engines (with fixture-citation
   comments so the reasoning survives), rebuilt + redeployed, conformance
   restored to 935/935. Reclassified INTENDED; the new guard test
   `test_mixed_calendar_ucum_year_month_equality_is_empty_fp01_historian`
   pins the fixture semantics (escaped-quote toQuantity forms + literal
   equivalents + ordering-empty + equivalence-true) so the prose-literal
   direction cannot silently return. This mirrors the SKEPTIC QA-005
   lesson in the opposite direction: prose-vs-fixture conflicts must be
   resolved by fixtures, in BOTH directions.

## Files changed (working tree, uncommitted)
Python engine:
- `fhir4ds/fhirpath/engine/invocations/equality.py` — QA-003
  `datetime_equality` plain-String-vs-FP_Time → empty (ResourceNode strings
  and Date/DateTime coercion unchanged); QA-001 guard kept as None with
  fixture-citation comment (revert artifact).
- `fhir4ds/fhirpath/engine/nodes.py` — QA-002: `_extractTimeByPrecision`
  T-less formats, `_plus_time` returns `FP_Time` node; QA-001 `__eq__`
  guards kept as None with fixture-citation comments.
Native (rebuilt twice + deployed to
`fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`):
- `extensions/fhirpath/src/fhirpath/evaluator.cpp` — QA-002: Time
  arithmetic result `result.string_val = buf` (no "T" prefix);
  QA-001 sites restored to -1 with fixture-citation comments.
Tests:
- `fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py` — 3
  new tests (fixture-pinned mixed-year-month empty; T-less time arithmetic
  render + type semantics; Time-vs-plain-String empty), 4 stale SKEPTIC
  expectations re-annotated with the fixture rationale (34 tests total).
- `fhir4ds/fhirpath/duckdb/tests/integration/test_arithmetic_parity.py` —
  7 stale T-prefixed time-arithmetic expectations updated to T-less.

## Validation (PROC_VALIDATION)
- Reproducer checks: 14/14 Python-core; 15/15 cross-engine zero-divergence
  matrix (pre-revert for QA-001 items, post-revert final state re-verified).
- HISTORIAN probes 1-4 (313 cases): **0 native↔fallback divergences** on
  the final state.
- `test_literal_parity.py` 34/34; literal+arithmetic+equality parity files
  169/169; fhirpath unit 178/178.
- Full fhirpath package pytest: **1575 passed, 0 failed**.
- CQL package pytest: **5631 passed, 9 skipped** (env skips), 0 failed.
- FINAL full conformance `run_all.py`: **2832/2832** (ViewDefinition
  144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47) — baseline held.
  Summary: `.temp/qa/fp01_historian_2026_08_16/final_conformance_summary.log`.

## Notes for Architect
- QA-001's terminal state is INTENDED (fixture-pinned), not RESOLVED — the
  "fix" was a no-op revert plus a guard test and code comments. The
  spec-prose-vs-fixture conflict (N1/master §6.1.1+§4.1.8 vs R4 fixtures
  lines 412-413) should be logged in AGENTS.md as a documented convention.
- The Date/DateTime-vs-plain-String coercion (`@2015-02-04 = '2015-02-04'`
  → true in both engines) remains a deliberate both-engine JSON-convenience
  convention that deviates from strict §5.5 (Explicit-only) reading;
  flagged for AGENTS.md, deliberately not changed (no fixture pins it;
  changing it risks JSON-field comparison breakage).
- Rebuild/deploy convention used: `cmake --build
  extensions/fhirpath/build/release -j 8` then copy
  `build/release/extension/fhirpath/fhirpath.duckdb_extension` to
  `fhir4ds/fhirpath/duckdb/extensions/`.
