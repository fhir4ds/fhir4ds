# QA Handoff — FP-06 HISTORIAN (iteration 1, 2026-08-17)

Chunk: FHIRPath §5.5.1 iif, §5.5.2 Boolean Conversion, §5.5.3 Integer Conversion.
Personality: HISTORIAN (systematic spec walkthrough; fresh angles beyond the
prior SKEPTIC launch's 209 clean probes).

## Method
- Fresh dual-path probe (123 cases): native `fhirpath.duckdb_extension` vs
  forced Python fallback, both through `SELECT fhirpath(?, ?)` +
  `fhirpath_is_valid(?)`. Probe: `/mnt/d/fhir4ds/.temp/qa/fp06_historian_2026_08_17/probe.py`
  (run with `PYTHONPATH=/mnt/d/fhir4ds`). Result: PASS=115, FAIL=8 raw flags.
- Fresh angles vs SKEPTIC launch: Unicode/exotic digit grammar, exact-Decimal
  arithmetic interplay (FP-01 seam), temporal/object/Quantity inputs,
  calendar/derived-unit equality inside iif criteria (FP-01/FP-02 seams),
  $this/$index/defineVariable scope inside iif branches, arity/validity,
  whitespace spellings, case-table corners, chaining into new-fix surfaces.

## Findings
Raw FAIL=8 decomposed: 4 probe-expectation errors (both engines agree,
spec-correct: comparison-error doctrine in iif criterion; $index semantics;
multi-item iif focus; out-of-range Integer literal → invalid in both engines),
2 genuine parity bugs, 1 doctrine note.

- **QA-001 (MEDIUM, CONFIRMED): fallback toInteger/convertsToInteger accept a
  single trailing newline.** `'1\n'.toInteger()` → fallback `1`, native empty
  (spec-correct: grammar is exact `(\+|-)?\d+`). `'-1\n'` too; `'1\n\n'`,
  `'\n1'`, `'1\t'` correctly rejected by both. Root cause: `intRegex`
  (`fhir4ds/fhirpath/engine/invocations/misc.py:15`) uses `$`, which in Python
  `re` matches before one final newline; needs `\Z`.
- **QA-002 (MEDIUM, CONFIRMED): fallback leaks defineVariable out of iif
  branch.** `iif(true, defineVariable('dv', 9).select(1), 2).select(%dv)` →
  fallback `9`, native empty. Native `fn_iif` (evaluator.cpp:7169) saves/
  restores `defined_variables_` after the criterion and scopes
  `chain_defined_vars_` per branch; Python `iif_macro` (misc.py:255) has no
  save/restore.
- **QA-003 (LOW, INTENDED): out-of-32-bit-range Integer literals evaluate to
  empty + is_valid=false identically in both engines** — consistent
  invalid-expression doctrine, not a bug.

## Verified clean (fresh coverage)
- Unicode digits (Arabic-Indic, fullwidth, Roman, mixed) rejected by both
  engines' toInteger/convertsToInteger/toBoolean.
- Exact-Decimal division seam: `(2/2).convertsToInteger()` → false (Decimal,
  not Integer) in both engines; `(1/3)`, overflow-promoted Decimal → false;
  `(2147483647+1).toInteger()` → empty (32-bit range).
- Temporal/object/Quantity inputs: `@2015-02-04.toBoolean()` empty /
  `.convertsToBoolean()` false; Quantity, JSON object, resource-root inputs →
  empty/false uniformly.
- iif criteria riding on FP-01/FP-02 equality fixes: `1 month = 30 days` → 'a';
  `1 'kJ' = 1000 'J'` → 1; `1 'm2/m' = 1 'm'` → 'y'; `1 month > 29 days` → 'gt';
  calendar-vs-UCUM empty equality → falls to otherwise-branch, both engines.
- Laziness: taken-branch errors propagate, dead-branch errors suppressed
  (arithmetic and singleton), nested dead iif suppressed, both engines.
- $this/$index inside iif in select; iif in where criteria; iif-in-repeat
  fixpoint (`1.repeat(iif($this<3,$this+1,{}))` → [2,3]).
- Case corners ('yEs','tRue','FALSE','T','F','Y','N') and invalid corners
  ('tr ue',' true','TrueX','0.00','1.00','-1.0','01') match N1 tables.
- Arity/validity: iif 1-arg/4-arg, convertsTo*(1) invalid on both surfaces.
- Chaining: `'2'.toInteger() * 3 'cm'` → `6 'cm'`; `'yes'.toBoolean() implies
  false` → false; calendar date add inside iif branch.

## Handoff to FIX
Fix QA-001 (`\Z` anchor) and QA-002 (scope save/restore in iif_macro,
mirroring native fn_iif). Both are Python-fallback-only; no native rebuild
needed. Verify probe goes 115→123 PASS and conformance holds 2832/2832.
