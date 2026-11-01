# Code Review — v0.0.14 WASM C++ Parity campaign (feature_implementation delta)

**Verdict: CLEAN_WITH_NOTES.** No CRITICAL/HIGH findings. All changes
verified against the feature plan §6 conditions (second-opinion adopted
conditions 1-7) and the repo's engineering standards.

## Scope reviewed (line-by-line)

Python: udf/datetime.py (deletions + camelCase regs), udf/conversion.py
(ConvertQuantity reg deletion), extension.py (conflicts-list additions),
loader/fhir_loader.py (native-mode macro reconciliation),
translator/expressions/_temporal_utils.py (whitelist entry removal),
4 test-file edits. C++: cql/math.{cpp,hpp} (cql_divide_text),
cql/ratio.{cpp,hpp} (ratio_compare), cql/valueset.{cpp,hpp} (coding_matches
family), cql_extension.cpp (7 new Funcs + registrations + cqlstructural
namespace). Web: cql-macros.ts ×2 apps, useDuckDB.ts ×2 apps,
playground.spec.ts. New: 6 parity test files, FEATURE plan, feature_handoff.

## Second-opinion condition verification (all 7)

1. fhir_loader fhirpath_in_valueset macro — RESOLVED (macro removed; C++
   registers both names; regression test
   test_native_loader_reconciliation). ✓
2. duckdb_functions() identity asserts per leg; no-Python leg LOADs raw
   binary. ✓ (all 6 parity files)
3. Differential byte-equality corpora — cqlDivide 3000, coding_matches 1200,
   cqlChildren/Descendants 800 cases, 0 diffs. ✓
4. cqlDateTimeAdd/ratioCompare divergent-input composite tests —
   documented + pinned (test_no_python_divergent_class_documented /
   test_ratio_compare_divergent_equivalence_documented). ✓
5. Pascal deletions — kept defs, camelCase regs; forced-python leg verified
   (weeksBetween/millisecondsBetween resolve; PascalCase case-insensitive
   fallback works). ✓
6. cqlDateTimeSubtract whitelist entry removed in same commit; 3 ConvertQuantity
   test callers edited to quantityConvert (1e100 boundary row re-expressed
   with justification comment). ✓
7. Native CQLMessage parity on LOAD-only con verified (macro-bearing cons
   keep both entries, macro wins — unchanged); 13/13 message parity tests. ✓

## Findings

- **REV-v14-001 (LOW, fixed in-review)**: orphaned comment "# Timezone
  normalization (CQL §22.1)" left after cqlNormalizeTZ deletion; stray
  double blank line in conversion.py. Both cleaned during review; imports +
  72 affected tests re-verified green.
- **REV-v14-002 (LOW, informational)**: ConceptToListCodeFunc on element
  normalization failure leaves unreferenced entries in the child vector
  (row count zeroed, validity invalidated) — harmless in DuckDB (child
  vector sized by SetListSize(total_size)) and matches the pattern used by
  ExtractCodesFunc; noted for the record, no action.
- **REV-v14-003 (LOW, pre-existing, out of campaign)**: web/website docs
  (notes-pipeline.md, terminology-service.md, docusaurus.config.ts) and
  conformance/reports/dqm_report.json appear modified in the working tree —
  not from this campaign (sibling session artifacts; dqm_report is a
  regenerated conformance artifact). Flagged for the scribe/release phases:
  dqm_report.json is regenerated output; website docs belong to the
  medterm4ds sibling effort.
- **REV-v14-004 (LOW, residual, owner FP-11)**: fhirpath
  test_math_parity one.ln()/zero.sqrt() cpp-bool False vs py-bool None —
  source-level divergence exposed by this campaign's fhirpath wasm/native
  rebuild (0.0.13 binary predated the Aug-26 evaluator.cpp edit). Not
  introduced here; documented in AGENTS.md campaign section + handoff.
- **REV-v14-005 (LOW, residual, owners recorded)**: 3 stale
  test_structural_type_parity tests (CQL-18 mixed-list doctrine drift) and
  the ratio `.numerator.value` accessor failure (CQL-20 HISTORIAN DEFERRED)
  — both pre-existing, verified pre-session.

## Memory-safety verification

- Fixed during dev (not in final tree): a use-after-free in ratio_compare
  (yyjson_doc_free before divide_ratio_components) — found via core-dump
  differential, fixed, and the fix verified with 600-case fuzz.
- Final tree stress: 600 ratioCompare + 600 structural-traversal fuzz + full
  malformed-input sweep across all 10 ported functions (empty/garbage/nested/
  NULL-op shapes) on the raw C++ connection — zero errors, zero crashes.
- Clobber guard: all 10 port symbols grep-verified in cql_extension.cpp and
  embedded in the wasm binary; binary md5 parity build==bundle==
  site-packages (native) and build==both web apps (wasm).

## Security

- No new injection surfaces: all UDFs take bound VARCHAR parameters; no
  string interpolation into SQL from user input. The cqlstructural
  serializer writes JSON through yyjson (escaped); LowercaseUnicodeEscapes
  only rewrites hex digits inside existing \uXXXX escapes.
- Web hooks change is display-layer only (Number rescale); no data exfil.

## Verification commands run (post-review)

- pytest: datetime 61 + conversion-check 12 (after cosmetic fixes)
- Memory-safety stress suite (see above)
- Gate re-verified earlier in phase: run_all.py 2832/2832

**Recommendation: PROCEED to spec_compliance phase.**

---

# Code Review #2 — post-evolution delta (step 6, 2026-09-09)

**Verdict: CLEAN_WITH_NOTES.** Reviewed the full working-tree diff vs HEAD
(49 paths; +3842/−4714 including regenerated artifacts) after the evolution
phase completed (15/15 iterations, domains 6-10).

## Delta reviewed beyond feature review #1

1. **iter-2 resolve()/Trim fix**: macros/clinical.py + fhir_loader.py both
   replace `TRIM(BOTH '"' FROM ...)` with `regexp_replace(ref, '^"|"$', '', 'g')`;
   clinical.py copy ALSO gained the versioned-ref `/_history/{vid}` strip
   (aligning it with the loader definition, which wins CREATE OR REPLACE in
   loader-then-register order — previously the clinical.py macro would have
   REVERTED versioned-ref support on that order; now both aligned).
   Regression test `test_resolve_macro_survives_cql_macro_registration`
   (2 orders × 7 ref forms) — 91/91 loader unit tests green. Doctrine
   recorded in cql/AGENTS.md (no 3-arg TRIM in CQL-macro-bearing SQL).
2. **extension.py conflicts additions**: cqlDateTimeAdd + ratioCompare with
   justified comments (dateAddQuantity sub-input-precision and CQL-03 QA-004
   compound-prefix divergence classes). Verified: desktop register() keeps
   Python authority for both names (macro shadowing), C++ scalars serve
   no-Python/WASM. Consistent with the 46-name pre-existing pattern.
3. **udf/datetime.py deletions**: cqlNormalizeTZ + cqlDateTimeSubtract
   def+registration removed; whitelist entry `cqldatetimesubtract` removed
   from _temporal_utils.py (same-commit per condition 6). Between-family
   regs renamed camelCase with explanatory comment (defs kept — forced-python
   leg sole provider). Verified zero remaining references.
4. **REV-v14-006 (LOW, fixed in-review)**: `ConvertQuantity` remained in
   udf/conversion.py `__all__` after its registration deletion — a stale
   public-export claim for a function no longer registered. Removed;
   import surface re-verified (CanConvertQuantity still legitimately
   imports ConvertQuantity internally).
5. **Web layer**: cql-macros.ts +4 BENCH-001 disambiguation macros with
   NULL-semantics comment (starts_with NULL → FALSE parity with desktop);
   useDuckDB.ts Arrow DECIMAL rescale (display-layer only, guarded by
   typeId===7 + finite-number check); playground.spec.ts +1 e2e
   (10.0/3.0 → 3.33 display, full native-cqlDivide + rescale proof).
   cql-clinic/ is a NEW untracked app (sibling effort, ships both wasm
   extensions, verify_lessons.py script) — flagged for scribe staging
   decision, not a code defect.
6. **Binary freshness (both legs)**: native cql 30c79e71 build(Sep 9
   01:24)==repo bundle==site-packages, newer than all C++ sources (latest
   ratio.cpp 01:23); fhirpath native unchanged 39bea478 (no fhirpath
   source diff — confirmed 0-line diff on extensions/fhirpath/src). WASM:
   cql 64e75d33 + fhirpath afe07dbd, build==wasm-demo==cql-clinic.
   dqm_report.json is regenerated conformance output (timing drift only).
7. **Untracked probe/scratch files** (REV-v14-007 LOW): web/wasm-demo/
   {clinic_lessons,clinic_one,probe2,probe3}.mjs + test-results/ are
   campaign probes — exclude from the commit; .opencode/ is config;
   llms.txt/robots.txt + website docs changes are the medterm4ds sibling
   session's work (coordinate at scribe; do not bundle into the campaign
   commit).

## Test verification (this review)

- 6 parity files re-run green post-`__all__` edit: divide 34 + coding 21 +
  structural 27 + datetimeAdd 56 + ratio/concept 77 + in_valueset 8 = 223.
- test_version 2 + message_parity 13; wasm gate + conversion-check +
  forced-backend 15; loader 91. Master gate 2832/2832 (held since evolution
  iter 2 fix).

## REV ledger carry-forward

Open pre-existing items unchanged: REV-002/003/005/009-016 (prior campaigns)
+ REV-v14-004 (FP-11 owner) + REV-v14-005 (CQL-18/CQL-20 owners) +
REV-v14-007 (scribe staging note). No new CRITICAL/HIGH at any point.

**Recommendation: PROCEED to pre_release.**
