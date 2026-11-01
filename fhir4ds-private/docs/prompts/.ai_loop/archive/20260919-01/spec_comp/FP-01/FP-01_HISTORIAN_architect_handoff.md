# Architect Handoff — FP-01 HISTORIAN Iteration 1 (2026-08-16)

## Structural health: SOUND
Golden standard: `.temp/architect/golden_standard_fp01_historian_iter1.md`
(the SKEPTIC iteration's 10 invariants + 4 new/extended ones: prose-vs-
fixture arbitration, canonical value storage, type-evidence discipline in
coercion, Recovery-Gate obedience). Audit covered this launch's FIX delta
(equality.py, nodes.py, evaluator.cpp, two parity test files) and the QA
phase quality.

## Findings by category
- Abstraction Integrity violations: 0 — engine semantics stayed in
  `fhir4ds/fhirpath/engine/**`; the DuckDB wrapper layer was not touched;
  the native change is at the value-construction site, not a render hack.
- Silent fallbacks / spec-gaming: 0 — QA-002/QA-003 fixes change the full
  class (all Time-arithmetic results across render/type paths; all
  plain-string Time peers); no test-specific branches. The QA-001 revert
  restored original semantics exactly and added fixture-citation comments
  in both engines plus a guard test, so neither the prose-literal nor any
  ad-hoc direction can silently return.
- Canonical-storage invariant: now enforced — Time values render T-less
  from every production path (literal, arithmetic result, toString(),
  text/json UDFs) in both engines; the §6.7 partial-time truncation rule
  survived the change.
- Layering violations: 0.
- Recovery-Gate obedience: FULL — the failed QA-001 attempt was reverted
  across source, tests, and the rebuilt/deployed extension binary, with
  the failure mechanism (missing `<output>` = expected-empty fixture
  contract) documented in code comments, AGENTS.md, and the guard test.
  No blind second attempt was made.

## Empirical parity audit
Probes 1-4 (313 cases) on the final state: **0 native↔fallback
divergences**. Guard tests: `test_literal_parity.py` 34/34 (3 new).
Full fhirpath package 1575/0 failed; fhirpath unit 178/178; CQL package
5631 passed/9 env-skipped; FHIRPath R4 935/935 (933/933+2 during the
reverted attempt, restored); FINAL full conformance **2832/2832**
(ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47).

## QA Enforcer Gate: NOT VETOED
QA executed a genuine systematic §4.1 walkthrough (all 8 subsections, 313
cases, dual spec versions fetched, official fixtures consulted, every
SKEPTIC fix re-verified including 3 previously-unprobed factor rows). One
quality note for the record (logged in GLOBAL_KNOWLEDGE, not veto-worthy
since the issue reached the correct terminal state through the Recovery
Gate): QA initially read the fixture's missing `<output>` as
"unspecified" instead of the harness's expected-EMPTY contract, which
mis-directed QA-001's fix. Future QA phases must treat fixture
output-absence as an explicit empty assertion at QA time.

## State hygiene
All 3 issues terminal (QA-001 INTENDED, QA-002/QA-003 RESOLVED);
evidence archived to ARCHIVE_LOG.md; evolution.json carries tombstones;
AGENTS.md gained the FP-01 HISTORIAN section (fixture-pinned empty
semantics, T-less Time values, Time-vs-String empty, Date/DateTime
JSON-convention note); GLOBAL_KNOWLEDGE.md gained the Evolution
Statistics row, three Recent-FHIRPath lessons, and the HISTORIAN
personality-effectiveness update.

## Compressed iteration summary (QA + FIX)
HISTORIAN QA walked §4.1 systematically across both engines (0 parity
divergences in the final state) and opened 3 issues; FIX resolved
QA-002/QA-003 in both engines (native rebuilt twice + deployed) and
drove QA-001 to the fixture-authoritative INTENDED outcome via a fully
reverted prose-literal attempt. Baseline 2832/2832 held throughout the
final state. Clean-exit criteria are met: zero non-terminal
CRITICAL/HIGH/MEDIUM issues, iteration ≥ min_iterations, exhaustive_mode
false.

## Recommended order for any future engineer
None required. Optional non-blocking observations:
- `FP_Time.__new__` returns None for invalid strings; `_plus_time`
  constructs `FP_Time` from a strftime result that is always valid, but a
  future constructor change could silently turn an arithmetic result into
  a None item — a debug assertion there would be cheap insurance.
- The Date/DateTime-vs-plain-String coercion convention (true/false by
  value in both engines vs strict §5.5 empty) remains a documented
  deliberate deviation; revisit only with a fixture mandate.
