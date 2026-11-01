# Engineer Handoff — Polish Feature (BUGFIX-001 through BUGFIX-006)

**Date:** 2026-08-11
**Engineer:** Remediation Engineer (autonomous, `.ai_loop`)
**Directive:** `fhir4ds-private/docs/prompts/.ai_loop/USER_DIRECTIVES.md`
**Source documents:** `FEATURE_PLAN_DRAFT_REVIEW.md` (external v1 plan review) + archived `code_review_findings.md` from prior cycle
**Baseline test totals (pre-fix):** viewdef 1117 / fhirpath 935 / sqlquery 28 = 2710 combined
**Post-fix totals:** viewdef 1118 / fhirpath 935 / sqlquery 29 = **2712 combined** (+2 new tests)
**Commits:** none yet — ready for staging on `dev`

---

## Summary

All 6 BUGFIX items resolved. Order followed USER_DIRECTIVES §Sequencing (BUGFIX-001 first since it touches the public error hierarchy; BUGFIX-005 + BUGFIX-006 last since both touch `test_parser.py`).

---

## Per-issue resolution

### BUGFIX-001 — `SQLError` inherits `SQLOnFHIRError` (HIGH)

**Files:** `fhir4ds/sqlquery/errors.py`, `fhir4ds/sqlquery/tests/test_smoke.py`

**Change:** `class SQLError(ValueError)` → `class SQLError(SQLOnFHIRError)`. `SQLOnFHIRError` already inherits from `ValueError`, so the broader `except ValueError` form still works transitively.

**Verified in:** new `test_error_hierarchy_inherits_sqlofhiriroot` in `TestPackageImports` (smoke) — asserts `issubclass(SQLError, SQLOnFHIRError)`, `issubclass(SQLError, ValueError)`, and behavioral catch of each typed subclass via `except SQLOnFHIRError`. All 29 sqlquery tests pass.

### BUGFIX-002 — cnl-0 single-char minimum length (HIGH)

**Files:** `fhir4ds/viewdef/parser.py`, `fhir4ds/viewdef/tests/unit/test_parser.py`

**Change:** added `len(vd.name) < 2` to the cnl-0 warning condition in `validate_view_definition()`. The condition is now `not vd.name[0].isupper() or len(vd.name) > 255 or len(vd.name) < 2`, matching the spec regex `^[A-Z]([A-Za-z0-9_]){1,254}$`.

**Verified in:** updated `test_single_char_name_warns` in `TestCnl0NameWarningPerSpecG2` — now asserts the warning fires for `name='A'` (previously documented the gap as accepted). All 5 cnl-0 tests pass.

### BUGFIX-003 — Spec test count `>= 144` floor (MEDIUM)

**Files:** `fhir4ds/viewdef/tests/test_spec_compliance.py`

**Change:** replaced strict `assert len(all_tests) == 144` with `>= MIN_EXPECTED_SPEC_TESTS` floor (constant = 144, with comment noting it's the FHIR/sql-on-fhir.js snapshot as of 2026-08-11). Added a helpful error message pointing at the upstream URL if the floor is violated. The existing diagnostic `print` above the assertion still logs the actual count.

**Verified in:** `TestSpecCoverage::test_spec_test_count` passes; manual inspection of the new floor assertion. Future suite growth above 144 will not break the runner.

### BUGFIX-004 — Gap analysis SUPERSEDED banner (LOW)

**Files:** `fhir4ds-private/docs/plans/SQL_ON_FHIR_V2_GAP_ANALYSIS.md`

**Change:** added a `⚠️ SUPERSEDED (2026-08-11)` blockquote banner at the top of the gap analysis pointing at the FDD, conformance report, release checklist, and joins-extension disclosure. Rest of the document preserved as historical context. Banner explicitly notes that gap-analysis claims (e.g., "134/134 stale", "9 of 22 files differ") were accurate as of 2026-08-11 morning and are no longer current.

**Verified in:** manual inspection. Banner is present; body content is unchanged.

### BUGFIX-005 — Rename `_extensions` → `extra_fields` (LOW)

**Files:** `fhir4ds/viewdef/types.py`, `fhir4ds/viewdef/parser.py`, `fhir4ds/viewdef/tests/unit/test_parser.py`, `fhir4ds/sqlquery/types.py`, `fhir4ds/sqlquery/parser.py`

**Change:**
- `ViewDefinition._extensions` → `ViewDefinition.extra_fields` with `field(default_factory=dict, repr=False, compare=False)`. The `repr=False, compare=False` flags keep the bag out of repr and equality semantics so existing dataclass equality assertions in tests are unaffected.
- Same rename for `_SQLLibraryBase._extensions` (the SQLQuery/SQLView analog).
- Updated parser construction sites: `viewdef/parser.py` (`extra_fields=extensions_bag`) and `sqlquery/parser.py` (`extra_fields=extensions`).
- Renamed `sqlquery/parser.py:_collect_extensions` → `_collect_extra_fields`.
- Updated `test_known_keys_are_not_treated_as_extensions` to use `parsed.extra_fields == {}`.

**Verified in:** `grep -rn "\b_extensions\b" fhir4ds/` returns nothing. `pytest fhir4ds/viewdef/ fhir4ds/sqlquery/` = 1146/1146 green (1117 viewdef + 29 sqlquery).

### BUGFIX-006 — `text.div` narrative roundtrip test (LOW)

**Files:** `fhir4ds/viewdef/tests/unit/test_parser.py`

**Change:** added `test_narrative_text_div_survives_roundtrip` to `TestCanonicalResourceRoundtripPerSpecG3`. Roundtrips a ViewDefinition with `text: {status: "generated", div: '<div xmlns="http://www.w3.org/1999/xhtml"><p>Hello</p></div>'}` and asserts JSON-level byte survival.

**FHIR JSON key verification:** confirmed `div` is the actual FHIR JSON key (not `_div`). The `_primitive` underscore convention in FHIR JSON applies only to primitive types carrying extensions; `Narrative.div` is a primitive `xhtml` but does not need underscore for the basic string form.

**Verified in:** new test passes; existing 7 §G-3 tests still green.

---

## Non-regression

- **viewdef:** 1117 → 1118 (+1 from BUGFIX-006 text.div test; BUGFIX-002 modified an existing test, no net add)
- **fhirpath:** 935 (unchanged)
- **sqlquery:** 28 → 29 (+1 from BUGFIX-001 error-hierarchy test)
- **Combined:** 2710 → **2712**, no regressions

---

## Out of scope (intentionally deferred)

These items from the external review and internal code review were not included in this polish cycle:

- **External review finding #6** (content-type precedence first-declared-wins documentation): behavior is correct in `select_best_content`; documentation could be clearer. Defer.
- **External review finding #7** (version bump recommendation): you chose `0.0.13`; no change.
- **External review finding #8** (rollback strategy): handled incidentally via separate commits in the prior feature.
- **External review finding #9** (latent generator risk): did not materialize; no follow-up needed.
- **External review finding #11** (`extensions/` subdir for joins-extension.md): only one extension right now; defer until a second surfaces.
- **Internal REV-001** (`_KNOWN_LIBRARY_KEYS` duplicate `relatedArtifact`): cosmetic, no functional impact. Defer to opportunistic cleanup.
- **Internal REV-002** (lazy imports in `runner.py`): harmless defensive style. Defer.

---

## Handoff to code_review

The diff from `e83631a5` (current `dev` HEAD) to the working tree contains:

| File | Change |
|---|---|
| `fhir4ds/sqlquery/errors.py` | `SQLError(SQLOnFHIRError)` (BUGFIX-001) |
| `fhir4ds/sqlquery/parser.py` | `_collect_extra_fields` rename + `extra_fields=` kwarg (BUGFIX-005) |
| `fhir4ds/sqlquery/tests/test_smoke.py` | new `test_error_hierarchy_inherits_sqlofhiriroot` (BUGFIX-001) |
| `fhir4ds/sqlquery/types.py` | `extra_fields` field with `repr=False, compare=False` (BUGFIX-005) |
| `fhir4ds/viewdef/parser.py` | cnl-0 min-length check + `extra_fields=` kwarg + comment update (BUGFIX-002, BUGFIX-005) |
| `fhir4ds/viewdef/tests/test_spec_compliance.py` | `>= 144` floor (BUGFIX-003) |
| `fhir4ds/viewdef/tests/unit/test_parser.py` | updated `_single_char_name_warns` (BUGFIX-002), renamed `_extensions` references (BUGFIX-005), new `text.div` test (BUGFIX-006) |
| `fhir4ds/viewdef/types.py` | `extra_fields` field with `repr=False, compare=False` + to_dict iteration update (BUGFIX-005) |
| `fhir4ds-private/docs/plans/SQL_ON_FHIR_V2_GAP_ANALYSIS.md` | SUPERSEDED banner (BUGFIX-004; private, gitignored) |

Recommended reviewer focus:
1. The `compare=False` flag on `extra_fields` — confirm no existing dataclass-equality test breaks beyond what we've already verified.
2. The `SQLError(SQLOnFHIRError)` inheritance — confirm no downstream code catches `SQLError` in a way that would be widened unexpectedly by the new parent.
3. The `>= 144` floor — confirm the diagnostic message is actionable.
