# Code Review Findings — Polish Feature (BUGFIX-001 through BUGFIX-006)

**Date:** 2026-08-11
**Reviewer:** Code Reviewer (autonomous, `.ai_loop`)
**Scope:** Commit `db1e4164` on `dev` (8 files, +97/-35)
**Audited against:** `evolution.json.issues[]` BUGFIX-001 through BUGFIX-006

---

## 1. Summary

**No new findings.** All 6 BUGFIX items correctly address their root causes. The diff is minimal, focused, and introduces no scope creep. Test totals: viewdef 1118 / fhirpath 935 / sqlquery 29 = **2712 combined** (+2 new tests; no regressions).

Pre-existing LOW findings from the prior cycle that were intentionally deferred (not in this feature's scope): REV-001 (`_KNOWN_LIBRARY_KEYS` duplicate `relatedArtifact`), REV-002 (lazy imports in `runner.py`). Both remain valid clean-up opportunities for an opportunistic future PR.

---

## 2. Per-issue verification

### BUGFIX-001 (HIGH) — `SQLError` inherits `SQLOnFHIRError` ✓

**Diff:** `fhir4ds/sqlquery/errors.py` — `class SQLError(ValueError)` → `class SQLError(SQLOnFHIRError)`. Added `from ..viewdef.errors import SQLOnFHIRError`.

**Verified:** `SQLOnFHIRError` already inherits from `ValueError` (confirmed via `fhir4ds/viewdef/errors.py`), so the transitive `except ValueError:` form still works. New test `test_error_hierarchy_inherits_sqlofhiriroot` asserts both `issubclass(SQLError, SQLOnFHIRError)`, `issubclass(SQLError, ValueError)`, and behavioral catch via `except SQLOnFHIRError`.

**Downstream audit:** `grep -rn "except SQLError\|except SQLQueryParseError\|except SQLQueryValidationError" fhir4ds/` returns nothing — no consumer catches `SQLError` directly in a way that the widened hierarchy would break. Consumers catching `SQLOnFHIRError` (the existing root) now transparently get SQLQuery errors, which is the intent.

### BUGFIX-002 (HIGH) — cnl-0 single-char minimum length ✓

**Diff:** `fhir4ds/viewdef/parser.py:validate_view_definition()` — condition extended with `or len(vd.name) < 2`.

**Verified:** Spec regex `^[A-Z]([A-Za-z0-9_]){1,254}$` requires 2-255 chars. New condition matches the regex's lower bound. `test_single_char_name_warns` correctly flipped from "document the gap" to "assert the warning fires".

**Downstream audit:** `grep -rn 'name="A"\|name='"'"'A'"'"'' fhir4ds/viewdef/tests/` returns nothing — no other test uses single-char `name` values that would now warn unexpectedly.

### BUGFIX-003 (MEDIUM) — `>= MIN_EXPECTED_SPEC_TESTS` floor ✓

**Diff:** `fhir4ds/viewdef/tests/test_spec_compliance.py` — strict `== 144` replaced with `>= MIN_EXPECTED_SPEC_TESTS` (constant = 144). Diagnostic message includes the actual count and the upstream URL.

**Verified:** Test passes (144 >= 144). Future upstream growth above 144 no longer breaks the runner. The `MIN_EXPECTED_SPEC_TESTS` constant is documented with the snapshot date.

### BUGFIX-004 (LOW) — Gap analysis SUPERSEDED banner ✓

**Diff:** `fhir4ds-private/docs/plans/SQL_ON_FHIR_V2_GAP_ANALYSIS.md` — added ⚠️ SUPERSEDED blockquote banner at top (gitignored; not in commit).

**Verified:** Banner points at FDD, conformance report, release checklist, joins-extension disclosure. Body preserved as historical context. Banner explicitly notes that gap-analysis claims are no longer current.

### BUGFIX-005 (LOW) — `extra_fields` rename ✓

**Diff:** 6 files touched. `ViewDefinition._extensions` → `extra_fields` and `_SQLLibraryBase._extensions` → `extra_fields` with `field(default_factory=dict, repr=False, compare=False)`. Parser construction sites updated. `_collect_extensions` → `_collect_extra_fields`. Test assertion updated.

**Verified:** `grep -rn "\b_extensions\b" fhir4ds/` returns nothing. The `repr=False, compare=False` flags keep the bag out of dataclass repr and equality semantics.

**Downstream audit:** `grep -rn "extra_fields=\|_extensions=" fhir4ds/viewdef/tests/` returns nothing — no test constructs a ViewDefinition with explicit `extra_fields` content for equality testing, so the `compare=False` flag does not silently relax any existing equality assertion.

### BUGFIX-006 (LOW) — `text.div` narrative roundtrip test ✓

**Diff:** `fhir4ds/viewdef/tests/unit/test_parser.py` — new `test_narrative_text_div_survives_roundtrip` in `TestCanonicalResourceRoundtripPerSpecG3`.

**FHIR JSON key verification:** The test uses `text: {status: "generated", div: "<div xmlns=...>...</div>"}`. The `div` key is correctly NOT underscored — FHIR JSON's `_primitive` underscore convention applies only to primitive types carrying extensions; `Narrative.div` is `xsd:xhtml` serialized as a plain string. Confirmed against FHIR R4 JSON serialization rules.

**Verified:** Test passes. JSON-level byte survival asserted via `json.dumps(..., sort_keys=True)` equality.

---

## 3. SQL injection analysis

No new SQL surface introduced. BUGFIX-001 changes a class hierarchy; BUGFIX-002 extends a Python conditional; BUGFIX-003 changes an assertion constant; BUGFIX-005 renames a dataclass field. None touch the SQL-generation or execution path.

---

## 4. Error hygiene audit

No new `except Exception` blocks. No new error-swallowing patterns. BUGFIX-001 widens the catchability of `SQLError` (a strictly additive change — consumers that previously caught `SQLError` still do; consumers that previously caught only `SQLOnFHIRError` now also catch it, which is the intent).

---

## 5. Architectural invariants

All 8 invariants from the prior feature's `ARCHITECT_REVIEW.md` remain preserved. The polish work does not touch the layering (I-1), validation strictness (I-2, I-6), parameter binding (I-3), extension bag (I-4 — renamed, behavior unchanged), `cnl-1` scope (I-5), `joins` extension (I-7), or spec test measurement (I-8 — `>= 144` floor is more permissive but does not weaken the measurement intent).

---

## 6. Findings summary

| ID | Severity | Subject | Recommended action |
|---|---|---|---|
| (none new) | — | — | — |

Pre-existing deferred items from prior cycle remain available for opportunistic cleanup:
- **REV-001** (LOW): `_KNOWN_LIBRARY_KEYS` in `sqlquery/parser.py` lists `relatedArtifact` twice. Cosmetic.
- **REV-002** (LOW): `sqlquery/runner.py` uses lazy imports inside methods unnecessarily.

Both are non-blocking. Neither was scoped into this polish feature.

---

## 7. Handoff

Code review complete. Pipeline `[bug_fix, code_review]` is fully executed:
- All 6 BUGFIX issues RESOLVED with `verified_in` citations
- No new findings
- Combined test totals: 2712/2712 green (no regressions)

Recommended next steps (human discretion):
1. **Commit `db1e4164` is on `dev`.** Push or PR when ready.
2. **Optional follow-up PR:** address REV-001 and REV-002 as opportunistic cleanup.
3. **Release 0.0.13:** the feature work (commits `050e5e78` + `e83631a5` + `db1e4164`) is ready for release engineering.

Setting `evolution.json.workflow: null` and `exit_reason: CLEAN` to signal clean exit.
