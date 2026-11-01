# SQL-on-FHIR v2 Spec Compliance Campaign — FINAL REPORT

**Generated:** 2026-08-24  |  **Fresh pass:** v1.1 (prior v1.0 pass disregarded per directive)

## Totals

- **Total chunks tested:** 58 / 58
- **Chunks passed:** 58
- **Chunks failed:** 0
- **Total bugs found:** 463
- **Total bugs fixed:** 325
- **Total bugs still open:** 0
- **Inner launches:** 174 (3 per chunk × 58)
- **Milestone code reviews:** 11 (spec_comp/reviews/review-{5,10,15,20,25,30,35,40,45,50,55}.md)
- **Mid-campaign reconciliations:** 2 (milestone-4 clobber recovery; CQL-05 DQM gate restoration)

## Per-section results

| Section | Chunks | Bugs found | Bugs fixed | Open |
|---|---:|---:|---:|---:|
| FHIRPath R4 | 20 | 153 | 103 | 0 |
| CQL 1.5 | 22 | 216 | 168 | 0 |
| SQL-on-FHIR ViewDefinition | 13 | 62 | 29 | 0 |
| SQL-on-FHIR Analytics Layer | 3 | 32 | 25 | 0 |

## Conformance gate (final tree)

- **OVERALL: 2832/2832 (100%)** — ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47
- Baseline held at every chunk finalization; all regressions caught by the recovery gate and root-caused.
- Extension binaries md5-matched repo==site-packages at campaign end (fhirpath 57d0634b…, cql c5b22d58…).

## Failed chunks

None. All 58 chunks passed with zero open bugs.

## Highest-impact fixes (subjective, by risk class)

- **2 CRITICALs (silent wrong results):** `exists` over dynamic lists false-with-data (CQL-18); deep-list alias defines truncation (CQL-18)
- **Silent wrong booleans:** interval comparison bound extraction (CQL-14/15); Code/Concept dynamic equality always-false (CQL-21)
- **Exactness:** 28-sig-digit Decimal arithmetic/power/division in native C++ (FP-01/FP-11); exact-typed aggregates (CQL-20/21)
- **Age uncertainty:** partial-birthDate age operators now spec-uncertainty-aware incl. in-list/negate/Min/Max (CQL-21)
- **Security/injection:** runner parameter path audited interpolation-free; identifiers sql-name validated + quoted (SOF-SQ-02/03)
- **Crash-to-typed-error:** recursion guards, segfault budget threads, typed ParseError/SQLQueryParseError boundaries throughout
- **Official-canonical recognition:** Shareable/Tabular + SQLQuery/SQLView profile canonicals corrected against machine-readable spec artifacts

## Open tracked debt (non-blocking, from milestone reviews)

- **REV-002** (MEDIUM, metadata drift): hand-maintained metadata maps across engines
- **REV-003** (LOW, hygiene): untracked files mixed into campaign tree
- **REV-005** (LOW, deprecation): mid-pattern inline regex flags in _compile_regex
- **REV-010** (MEDIUM, accretion): viewdef generator shape-selection carve-outs
- **REV-011** (LOW, perf): aggregate macro re-anchoring
- **REV-012** (MEDIUM, parity): cqlUncertain* dual-implementation parser drift
- **REV-013** (LOW, informational): fhirVersion 63-code binding note
- **REV-014** (MEDIUM, parity): fallback temporal±UCUM validity flag (5 edges)
- **REV-015** (MEDIUM, parity): native replaceMatches named-group substitution
- **REV-016** (LOW, thread-safety): recursion-budget global mutation under setters-only lock
- REV-001/004/006/007/008 resolved during the campaign; REV-009 (FHIRHelpers loader) terminal-UNCONFIRMED after 4 consecutive green DQM runs.

## Notable doctrine adjudications (AGENTS.md NOT A BUG registry)

- Fixtures/machine-readable spec artifacts outrank spec prose (multiple adjudications incl. `as` exact-match, cnl-1 WARNING severity, ToTime timezone acceptance).
- Population-level boolean defines encode null→FALSE membership semantics (expression-level stays spec-correct).
- DQM-load-bearing conventions preserved through all list/shape machinery (CMS128/117/122/124/125/130/1017/832 regressions each root-caused, never papered over).

## Working-tree state

All campaign fixes are uncommitted in the working tree of /mnt/d/fhir4ds (branch dev), per campaign constraints. Archive at spec_comp/ (58 chunk dirs, 11 reviews, 2 reconciliations). Knowledge files compacted at milestones; GLOBAL_RULES.md carries the durable invariants.
