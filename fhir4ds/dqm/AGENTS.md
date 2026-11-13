# fhir4ds.dqm AGENTS.md

Institutional memory for the DQM (Digital Quality Measure) sub-package.

## Package layout

- `evaluator.py` — `MeasureEvaluator` orchestrator. Public entry:
  `evaluate(measure_bundle, cql_library_path, parameters, audit_mode, ...)`
  and `compile_measure`/`execute_compiled_measure` for reuse.
- `audit.py` — `AuditEngine`: relevance-prune evidence per population
  persona.
- `narrative.py` — `NarrativeGenerator`: human-readable fragments from
  grouped evidence.
- `parser.py` — `MeasureParser`: FHIR Measure JSON → `PopulationMap`.
- `types.py` — `AuditPersona`, `AuditMode`, `AuditOrStrategy`,
  `PopulationEntry`, `GroupMap`, `PopulationMap`, `SupportingEvidenceDef`.
- `artifacts.py` — `ArtifactResolver` family (file/HAPI), `LibraryArtifact`,
  `MeasureArtifact`, `ValueSetRef`.
- `models.py` — `MeasureResult` dataclass.
- `errors.py` — `DQMError`, `MeasureParseError`.
- `tests/conformance/` — the conformance runner used by
  `conformance/scripts/run_dqm.py`.

## Population attribution model

`MeasureEvaluator._population_masks` (evaluator.py:592-613) builds:
- `denom_after_excl_mask = denom_mask & ~denom_excl_mask`
- `numer_mask = denom_after_excl_mask & population_mask("numerator")`
- `denom_except_mask = denom_after_excl_mask & ~numer_mask & population_mask("denominator_exception")`

`_prune_population_evidence` (evaluator.py:1456-1570) post-processes audit
cells: only `AuditPersona.EXCLUSION` cells get evidence pruning based on
`effective_result`. Inclusion and numerator cells pass through with their
raw SQL evidence intact.

## Architectural Invariants (Domain 9 audit)

- **Inner-clause audit macros must not be load-bearing for evidence.**
  When audit_and/or/not/leaf macros appear inside the WHERE clause of a
  correlated EXISTS subquery (e.g., with-such-that conditions, retrieve
  filters), they MUST be eliminable without losing audit evidence. The
  OUTER per-patient audit CTE in cte_manager.py (which wraps the entire
  definition as `audit_leaf(EXISTS(...))`) is the canonical evidence
  capture point; inner macros are redundant duplicates. Violating this
  invariant triggered QA-016 (DuckDB binder error on CMS71/CMS996).

- **The `_pt` alias is the canonical outer patient correlation alias.**
  Any SQL emitted in a sub-query context that references the outer
  patient table MUST use `_pt.patient_id` (correlation.py:373). The
  legacy `p.patient_id` references are unbound and trigger
  `BinderException: Referenced table "p" not found`. The
  `replace_qualified_alias` text-rewriter only matches `_pt.patient_id`.

## Known Fragile Areas (Domain 9 audit)

1. **`audit_mode='full'` SQL emission binder failures (FIXED iter-7)** —
   QA-016 (RESOLVED). The original bug had two failure modes:
   (a) `Referenced table "p" not found!` — fixed by replacing the
   unbound `p` alias with `_pt` in 5 sites: 3 in
   `fhir4ds/cql/translator/ast_helpers.py::_inject_audit_evidence`
   (lines ~1698/1712/1725) and 2 in
   `fhir4ds/cql/translator/cte_manager.py` audit CTE pre-compute lookup
   (lines ~614/622).
   (b) `Need named argument for struct pack` — fixed by introducing
   `_fully_demote_audit_to_bool` in
   `fhir4ds/cql/translator/expressions/_query.py:114-235`. The fix
   detects when an audit_xxx chain contains an `audit_leaf` wrapping a
   complex argument (EXISTS subquery or non-trivial function call like
   intervalContains/coding_matches) and recursively eliminates all
   audit_and/or/not/leaf macros from the boolean expression, producing a
   plain boolean that DuckDB's binder can plan safely. The audit evidence
   is preserved by the OUTER per-patient audit CTE in cte_manager.py
   which wraps the entire definition as `audit_leaf(EXISTS(...))`. The
   inner WHERE-clause audit macros were redundant — they would have
   produced duplicate evidence that the outer CTE already captures.
   Defense-in-depth: an explicit `_fully_demote_audit_to_bool` call is
   also made at the with-such-that translation site
   (`_query.py:4885-4906`). After the fix, 4/5 sampled CMS measures pass
   FULL audit (CMS135, CMS165, CMS71, CMS996). CMS2 is legitimately
   skipped (SQL > 350k chars). The conformance runner still silently
   falls back to non-audit SQL (`runner.py:201-213`) when audit fails,
   but this no longer triggers for the sampled measures.

   **Note on action hint:** the public API
   `MeasureEvaluator.evaluate(audit_mode='full')` may still wrap
   binder errors with a hint pointing to `audit_mode='population'` —
   see `fhir4ds/dqm/evaluator.py::_maybe_wrap_audit_binder_error`.
   POPULATION mode remains the recommended production path for all
   measures and is unaffected by any audit-emission binder quirks.

2. **POPULATION audit mode emits no evidence for boolean-combination
   definitions** — QA-018 (FIXED in iter-7). `evaluator.py:_generate_narrative`
   line ~1646 hardcoded `evidence_captured = audit_mode != POPULATION`,
   hiding concrete resource evidence behind the generic
   "evidence not captured in this audit mode" message. The fix makes
   `evidence_captured` reflect whether the cell actually has evidence
   (`bool(ev_dicts) or audit_mode == FULL`). Note: POPULATION mode still
   emits no `_audit_item` for boolean-combination definitions upstream
   (ast_helpers.py); the iter-7 fix only ensures that when evidence IS
   present, the narrative uses it.

3. **Numerator evidence not pruned when patient is in denominator_exclusion**
   — QA-017 (FIXED in iter-7). `_prune_population_evidence` only acted on
   `AuditPersona.EXCLUSION` cells; numerator cells kept their SQL-emitted
   evidence, which was often the denominator criterion (LVSD Encounter)
   rather than the numerator criterion (MedicationRequest). The fix
   extends `_prune_population_evidence` to detect when a patient is in
   `denominator_exclusion` and short-circuits the numerator cell,
   replacing its evidence with `[]` and setting `effective_result=False`.

4. **Conformance runner hardcodes `audit=False`** — QA-019 (FIXED in
   iter-7). `conformance/scripts/run_dqm.py` now accepts a `--audit` CLI
   flag that enables audit-mode SQL emission (POPULATION tier). Default
   remains `audit=False` to preserve the historical 47/47 baseline; CI
   can opt in via `--audit` to surface audit emission bugs.

## NOT A BUG Registry

- **`denominator_exception` masking when patient is in numerator**:
  correctly sets `effective_result=False` when numerator is True. Per
  CMS eCQM Logic Guidance, exceptions only apply when patient is NOT in
  numerator.

- **Resource ID traceability format**: every evidence `target` is a
  well-formed `ResourceType/id` string (e.g., `Encounter/abc-123`).

- **Exclusion-persona pruning for non-excluded patients**: when a patient
  has denominator_exclusion criteria raw=True but is NOT in denominator
  (e.g., failed IP), `effective_result=False` correctly prunes the
  evidence.

- **Deduplication of audit rows in FULL mode**:
  `_execute_compiled_group` (evaluator.py:1411-1419) drops Cartesian-
  product duplicates by `patient_id` keep=first.

## Measurement Period gotcha

The 2025 conformance suite (ecqm-content-qicore-2025) uses MP
**2026-01-01..2026-12-31** for ALL measures (per
`load_test_suite` → `test_suite.measurement_period`). Tests/probes that
pass `parameters={"Measurement Period": ("2025-01-01", "2025-12-31")}`
will silently return all False — the test fixtures are dated 2026. Always
use the test-suite MP or look it up via `load_test_suite`.

## Conformance runner audit tier strategy

The runner (`runner.py:111-291`) uses three tiers based on non-audit SQL
size:
- `< 200KB`: try FULL audit
- `< 350KB`: try POPULATION audit if FULL failed
- `>= 350KB`: skip audit entirely

Silent fallback to non-audit SQL happens at runner.py:292-293
(`audit_fallback = True`). This is the mechanism that masks QA-016 from
the release gate.

## Iteration 13 / Domain 9 SKEPTIC — attribution truth table (measured, not asserted)

`MeasureEvaluator.summary_report()` was verified against a PROSE-derived oracle
on the complete 2^6 space of the six CQM populations (64 synthetic patients) and
on the inert-population edge cases. Result: exact match, no source change.

Rules the oracle encodes (use them when writing attribution tests):

- every population is gated by the initial population;
- `denominator_exclusion` is evaluated BEFORE the numerator and short-circuits
  it: an all-True patient ends with `numerator`=0 and `numerator_exclusion`=**0**
  (numerator exclusion applies only INSIDE a numerator). A fixture that sets all
  six flags true therefore cannot exercise numerator exclusion;
- `denominator_exception` applies only to denominator members that are not
  excluded and did NOT meet the numerator; when withheld, the patient stays in
  `denominator_final` AND counts in `numerator_final`;
- numerator outside the denominator, exclusions outside their scope, and
  everything outside the initial population are all inert;
- audit cells shaped `{"result": bool, "evidence": [...]}` are read via
  `.result`; the same short-circuit applies, so an all-True audit frame is a
  denominator exclusion, not a numerator — a shape test must use a realistic
  cell (IP + denominator + numerator true, exclusions false);
- `to_measure_report()` without a prior `evaluate()` raises
  `DQMError("No evaluation has been run yet. Call evaluate() first.")`;
- multi-group summaries equal each group's own slice and their IPs sum to the
  overall total.

## Iteration 14 / Domain 9 HISTORIAN — evidence/narrative contract (pinned)

- `AuditEngine.prune_evidence(row, population_code, persona)` is ROW-oriented:
  the cell must be wrapped as `{column: cell}` with `column` =
  `population_code.replace("-", "_")`. Passing the raw cell silently returns
  `[]` (evidence dropped, no error) — the documented trap. Every caller must
  wrap.
- Persona relevance: `EXCLUSION` keeps evidence only when the criterion is
  satisfied ("only_when_excluded"); `INCLUSION`/`NUMERATOR` always keep it.
  Empty evidence and scalar (non-struct) cells return `[]`.
- Compaction groups by `(trace, attribute, operator, threshold)`; same-key
  findings merge into one group (narrative renders `(+1 more)`). A trace-less
  item is its OWN bucket — counting groups as "items - merges" undercounts
  because of it. Hostile thresholds (`{"value": 1}`, `[1, 2]`) must stay
  hashable in the group key, non-dict items are skipped, and output stays
  JSON-serialisable.
- `NarrativeGenerator.generate()` wording states are contractual: not-met with
  no evidence → "no detailed evidence available"; not-met with
  `evidence_captured=False` → "evidence not captured in this audit mode";
  met with no evidence → "criteria met"; unknown population code → generic
  `Evidence:` header.

## Iteration 15 / Domain 9 EXPLORER — audit mode verified on real measures

Ran CMS165 and CMS122 twice each (audit off/on) on the shipped qi-core-2025
fixtures. Pinned results:

- Enabling audit does NOT change population results (68/56 patients identical).
- The one-row-per-patient contract holds with evidence attached (68 rows/68
  patients; 56/56) — the historical evidence-JOIN fan-out stays fixed.
- Every evidence `target` resolves to a real resource id: 152/152 (CMS165) and
  116/116 (CMS122) cited ids exist in the `resources` table. Use this check
  (cite → resolve → compare counts) whenever audit evidence changes.
- Population/criteria (Boolean) columns are `{result, evidence}` structs; with
  `all_columns=True` non-Boolean definitions stay plain (`list`/`float`/`None`).
  The invariant is per-COLUMN ("no column mixes struct and scalar"), not
  "every cell is a dict".
- Two consecutive audit runs are identical (deterministic).

API TRAP: `fhir4ds.dqm.tests.conformance.runner.run_measure()` returns its own
`MeasureResult` with `.results` (list of per-patient dicts), NOT `.dataframe`
— that attribute belongs to `fhir4ds.dqm`'s `MeasureResult`. Probes must use
`.results`.
