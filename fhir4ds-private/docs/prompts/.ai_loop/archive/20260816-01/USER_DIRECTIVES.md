# 🎯 USER DIRECTIVES

<!--
This file is the PRIMARY MANDATE for the AI Initializer.
Edit this file to define your strategic goals, pipeline, and focus areas.
-->

## Strategic Goal

Close the review findings on the SQL-on-FHIR v2 spec compliance + Analytics
Layer feature (commits `050e5e78` and `e83631a5` on `dev`). The external
plan review (`fhir4ds-private/docs/prompts/.ai_loop/FEATURE_PLAN_DRAFT_REVIEW.md`,
written against v1 of the prior FDD) surfaced six items that the v2 refinement
and implementation only partially addressed. The internal code review
(`code_review_findings.md` from the prior cycle) logged four LOW findings
(REV-001..004). This feature drives all of them through remediation and
re-review.

The feature is **scoped to the findings list below**. Anything not listed
is out of scope. Non-regression on the combined 2710-test viewdef+fhirpath+
sqlquery suite is a hard constraint — any fix that regresses tests must
preserve the existing green baseline or back out.

## Pipeline

1. `bug_fix` — Remediation Engineer addresses the seeded issues
2. `code_review` — Code Reviewer re-audits the diff

Skip `feature_design` — fixes are well-specified, no architecture choices.

## Specific Bug Fix

Six issues seeded directly into `evolution.json.issues[]` (see Initializer).
Severity ordering below is the recommended remediation order; the Remediation
Engineer may reorder if dependency or efficiency considerations apply.

### BUGFIX-001 (HIGH) — `SQLError` error-model integration

`fhir4ds/sqlquery/errors.py` defines `SQLError(ValueError)`. The external
review (finding #5) recommended `SQLError` inherit from the existing
`fhir4ds.viewdef.errors.SQLOnFHIRError` root so consumers catching
`SQLOnFHIRError` also catch SQLQuery errors. Fix: change the base class
to `SQLOnFHIRError`; verify `SQLError` still inherits from `ValueError`
transitively (since `SQLOnFHIRError` already does). Add a unit test
asserting `except SQLOnFHIRError` catches a `SQLQueryParseError`.

**Validation:** `pytest fhir4ds/sqlquery/` green; new unit test passes;
existing test assertions on `ValueError` parent still hold.

### BUGFIX-002 (HIGH) — `cnl-0` single-character name gap

`fhir4ds/viewdef/parser.py:validate_view_definition()` checks
`not vd.name[0].isupper() or len(vd.name) > 255` for the cnl-0 warning,
but the spec regex `^[A-Z]([A-Za-z0-9_]){1,254}$` requires 2-255 chars.
A name like `"A"` violates cnl-0 but currently passes. This is REV-004
from the prior code review. Fix: add `len(vd.name) < 2` to the warning
condition. Add a unit test asserting the warning fires for `name='A'`.

**Validation:** `pytest fhir4ds/viewdef/tests/unit/test_parser.py::TestCnl0NameWarningPerSpecG2`
green; the `test_single_char_name_warns` test should flip from "document
the gap" to "assert the warning fires".

### BUGFIX-003 (MEDIUM) — Brittle spec-test count assertion

`fhir4ds/viewdef/tests/test_spec_compliance.py` line 633 asserts
`assert len(all_tests) == 144`. The external review (finding #3) recommended
`>= 144` with a logged count, so the next upstream suite growth does not
break the runner. Fix: change to `assert len(all_tests) >= 144` and log
the actual count via `print` (matching the existing diagnostic pattern
above the assertion).

**Validation:** `pytest fhir4ds/viewdef/tests/test_spec_compliance.py::TestSpecCoverage::test_spec_test_count`
green; manual inspection of the assertion.

### BUGFIX-004 (LOW) — Gap analysis superseded banner

`fhir4ds-private/docs/plans/SQL_ON_FHIR_V2_GAP_ANALYSIS.md` is now stale
— its "Compliance Summary" table claims "134/134 stale, 9 of 22 files
differ", both resolved by the §G-5 spec suite refresh. Add a banner at
the top: "Status: SUPERSEDED. This gap analysis was the input to the
SQL-on-FHIR v2 spec compliance feature (commits `050e5e78` + `e83631a5`).
The durable artifacts are the FDD at
`fhir4ds-private/docs/architecture/plans/FEATURE_SQL_ON_FHIR_V2_SPEC_COMPLIANCE.md`
and the post-implementation conformance report at
`conformance/reports/final_compliance_report.md`."

**Validation:** Banner present; no other changes to the gap analysis
content (preserve historical context).

### BUGFIX-005 (LOW) — `_extensions` dataclass field rename

`fhir4ds/viewdef/types.py:ViewDefinition._extensions` uses a leading
underscore, which the external review (finding #2) and the prior code
review (REV-003) both flagged as unconventional for a dataclass field.
Rename to `extra_fields: Dict[str, Any] = field(default_factory=dict,
repr=False, compare=False)`. The `repr=False, compare=False` flags keep
the bag out of dataclass equality and repr semantics. Update
`viewdef/parser.py` (construction site), `viewdef/types.py` (to_dict
emission), and the `TestCanonicalResourceRoundtripPerSpecG3` tests.

**Public API churn warning:** the field name is part of the
`ViewDefinition` dataclass surface. The feature shipped in `0.0.13` and
no one is consuming it externally yet, so churn is contained.

**Validation:** `pytest fhir4ds/viewdef/` green; updated tests pass;
`grep -rn "_extensions" fhir4ds/` returns nothing.

### BUGFIX-006 (LOW) — Explicit `text.div` roundtrip test

The §G-3 roundtrip tests cover nested extension arrays and `meta.tag`
arrays, but not specifically DomainResource `text` narrative. The
external review (finding #1) wanted an explicit `text: {"status": "generated", "_div": "<div xmlns=...">...</div>"}` roundtrip test asserting
byte-for-byte survival of the inner structure. Add it to
`TestCanonicalResourceRoundtripPerSpecG3`.

**Note:** FHIR JSON uses `_div` (with leading underscore) for the XHTML
narrative div — verify the actual key name against FHIR JSON serialization
rules before writing the test.

**Validation:** New test passes; no implementation change required (the
extension bag already preserves nested structure verbatim).

## Focus Areas

### Sequencing (must-follow)

- **BUGFIX-001 first.** The error-model fix touches the public `SQLError`
  hierarchy and may affect error-catching tests downstream. Land it
  before the other fixes so any test fallout is isolated.
- **BUGFIX-002 second.** Spec-compliance gap with a one-line fix.
- **BUGFIX-003 + BUGFIX-004 next.** Both are trivial; bundle into one
  commit if convenient.
- **BUGFIX-005 + BUGFIX-006 last.** Both touch tests; the rename in
  BUGFIX-005 will require touching the same test file BUGFIX-006 adds to.

### Cross-cutting

- **No regressions** on `pytest fhir4ds/viewdef/ fhir4ds/fhirpath/ fhir4ds/sqlquery/`
  (currently 2710/2710 green).
- **Commits:** one commit per bug fix is preferred for reviewability;
  bundle only BUGFIX-003 + BUGFIX-004 if convenient.
- **No new public API surface** beyond the rename in BUGFIX-005 (which
  replaces one name with another).

## Specific Bug Fix Validation

After the Remediation Engineer finishes all six fixes, the Code Reviewer
re-audits:

1. The diff from `HEAD` (currently `e83631a5`) to the new HEAD.
2. Confirm each BUGFIX issue in `evolution.json.issues[]` is `RESOLVED`
   with a `verified_in` field referencing the test or inspection that
   proves the fix.
3. Confirm no new findings beyond what was already known.

If the Code Reviewer finds new issues, they get seeded back into
`evolution.json` and the human decides whether to do another remediation
pass or ship as-is.
