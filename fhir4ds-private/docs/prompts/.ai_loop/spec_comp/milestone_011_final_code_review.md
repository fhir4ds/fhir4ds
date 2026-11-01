# Milestone 11 (FINAL) Code Review — chunks SOF-VD-09..SOF-SQ-03

## Verdict: MILESTONE PASS — SWEEP COMPLETE 58/58

Final standing suites re-verified FRESH: 94 passed (160.23s).
Log: .temp/qa/speccomp2/final_suites.log.

## Evidence audit (8 chunks, this window)
- SOF-VD-09 (where): SKEPTIC 20/20 + H/E 12/12 green. AND semantics; false/
  empty/null exclude; iterated-focus evaluation in forEach (%resource for
  root scope); typed ParseErrors; official logic.json fixture semantics
  (deceasedBoolean absent vs present-false).
- SOF-VD-10 (validation rules): SKEPTIC 31/31 + H/E 22/22. sql-name all 3
  name kinds; at-most-one row generator; required fields; resource +
  fhirVersion (ARRAY) bindings; branch-vs-branch unionAll mismatch
  (fixture-pinned); constant items permissive.
- SOF-VD-11 (execution): SKEPTIC 7/7 + H/E 12/12 + official compliance
  465 passed (incl. 144 spec_tests parity, FRESH RERUN). Array unrolling;
  type coercion; iterated-focus columns; empty-table semantics.
- SOF-VD-12 (metadata/profiles): SKEPTIC 12/12 + H/E 22 checks. Shareable/
  Tabular enforcement; full CanonicalResource round-trip incl. to_dict ->
  parse identity; XML typed rejection; unknown keys verbatim retention.
- SOF-VD-13 (invariants): SKEPTIC 19/19 + H/E 11/11. cnl-1 WARNING
  severity on url (space = lexical error); Column.type exempt; same-vs-
  cross resource element-ID; canonical |version forms; cnl-0 WARNING;
  extra_fields repr/compare isolation.
- SOF-SQ-01 (Library parsing): SKEPTIC 16/16 + H/E 8/8. Profile dispatch
  (dual canonicals, |version); LibraryTypesCodes binding; content
  cardinals + base64-UTF-8; application/sql prefix invariant.
- SOF-SQ-02 (runner): SKEPTIC 12/12 + H/E 9/9. Materialization chains;
  cycles pre-execution; dialect selection; :name prepared binding w/
  FHIR-type coercion; label/param sql-name; idempotency; diamond graphs.
- SOF-SQ-03 (integration): SKEPTIC 15/15 + H/E 7/7. 1/2/3-level chains;
  innermost-failure context; ambiguous dict rejection; error hierarchy
  (SQLError <- SQLOnFHIRError <- ValueError); one-way dependency; full
  public API.

## Sweep totals
58/58 chunks PASSED (FP-01..20, CQL-01..22, SOF-VD-01..13, SOF-SQ-01..03),
each with 3 personalities (SKEPTIC + combined H/E battery; exception
ledger for CQL-05/11/12/15/16/17 documented in earlier milestone reviews).
0 bugs found / 0 fixed across the entire sweep. 4 open LOW findings,
findings-only discipline (never patched; human triage):
- FP-10-F01: FHIRPath matches() 's'-flag native-lenient vs fallback-strict
  (spec §5.6.9 lists only m/i; needs native rebuild when fixed).
- FP-14-F01: birthDate < non-date-shaped-string ordering native-lexicographic
  vs fallback §6.2-strict-empty (resource-FIELD corner unpinned).
- FP-18-F01: Boolean×Quantity `true * 5 'mg'` fallback-coerces vs native
  rejects (fix dir: Boolean guard in engine math quantity-multiply + pin).
- CQL-21-F01: ToConcept equality fallback crash (TypeError float() NoneType;
  native False is spec-correct; fix dir: guard float() in concept-equality
  fallback chain + parity pin).

All evidence archived under spec_comp/{CHUNK}/ (12 files per chunk) +
milestone_001..011 reviews. Probe corpus: .temp/qa/speccomp2/ (~40 scripts).
