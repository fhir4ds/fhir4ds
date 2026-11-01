# Code Review Findings — SQL-on-FHIR v2 Spec Compliance + Analytics Layer

**Date:** 2026-08-11
**Reviewer:** Code Reviewer (autonomous, `.ai_loop`)
**Scope:** Two commits on `dev` vs `main`: `050e5e78` (Steps 1-6) + `e83631a5` (Steps 7-8)
**Audited files:** `fhir4ds/sqlquery/*` (new), `fhir4ds/viewdef/{types,parser,generator,utils,__init__}.py`, `fhir4ds/viewdef/tests/test_spec_compliance.py`, `fhir4ds/fhirpath/engine/invocations/datetime.py`

---

## 1. Summary

**No CRITICAL or HIGH findings.** Four LOW findings, all in the new `fhir4ds/sqlquery/` package or in the §G-2/§G-3 additions. The implementation is structurally sound, follows project invariants, and the SQL injection threat model is correctly scoped (author-controlled raw SQL is intentional; caller-controlled parameters go through DuckDB prepared statements only).

**Issues filed:** REV-001 (LOW, cosmetic), REV-002 (LOW, readability), REV-003 (LOW, naming), REV-004 (LOW, spec interpretation gap).

---

## 2. SQL injection analysis (CRITICAL-axis audit)

The new `fhir4ds/sqlquery/runner.py` is the primary SQL-surface addition. Audit:

| Call site | Input source | Defense | Verdict |
|---|---|---|---|
| `self._con.execute(f'CREATE OR REPLACE VIEW {quoted_label} AS {view_sql}')` | `label` from relatedArtifact; `view_sql` from ViewDefinition generator OR SQLView content.data | `quoted_label` from `viewdef.utils.quote_identifier` (sql-name validated); `view_sql` is intentionally author-controlled per spec threat model | **SAFE** |
| `self._con.execute(sql_body, params)` | `sql_body` from `content.data` (author-controlled); `params` from caller | `sql_body` is author-controlled (intentional); `params` go through DuckDB prepared-statement binding (no string interpolation) | **SAFE** |
| `self._con.execute(sql_body)` (no params path) | same as above | same | **SAFE** |

No f-string SQL with caller-controlled values. No `.format()` SQL patterns. The `_SAFE_IDENTIFIER_RE = ^[a-zA-Z_][a-zA-Z0-9_]*$` regex on `quote_identifier` rejects injection payloads containing whitespace, quotes, semicolons, etc.

**ViewDefinition-side changes:** `NULLIF(fhirpath_text(...), '')` wrap inserts a fixed SQL function template around the existing fhirpath_text call. No new injection surface.

---

## 3. Model knowledge in logic audit

Per `GLOBAL_RULES.md` "Model Knowledge Must Be Data-Driven":

- `_FHIR_TYPE_TO_DUCKDB` dict in `fhir4ds/viewdef/types.py` is the single source of truth for FHIR-type → DuckDB-type coercion. New types added by editing the dict, not by adding branches. ✓
- `_CANONICAL_RE` is a single module-level regex, not duplicated across call sites. ✓
- `_KNOWN_TOP_LEVEL_KEYS` frozenset in `viewdef/parser.py` centralizes the ViewDefinition known-keys set used by the §G-3 extension-bag collector. ✓
- `_KNOWN_LIBRARY_KEYS` frozenset in `sqlquery/parser.py` mirrors this for Library resources. (See REV-001: contains a duplicate entry; cosmetic.)
- No resource-specific branches (`if resource_type == "Observation"`) added in generic paths. ✓
- No profile URL maps, measure IDs, or hardcoded FHIR constants in the new code. ✓

---

## 4. Error hygiene audit

Two new `except Exception` blocks in `fhir4ds/sqlquery/`:

1. **`parser.py:126`** — wraps `base64.b64decode(raw_data).decode("utf-8")` which can raise `binascii.Error` or `UnicodeDecodeError`. Re-raises as `SQLQueryParseError` with `from exc`. ✓ Acceptable translation pattern.
2. **`runner.py:159`** — wraps the caller-supplied `resolver(canonical)`. Since the resolver is opaque, catching broad `Exception` and re-raising as `SQLQueryMaterializationError` is acceptable defensive practice. ✓

Neither block silently swallows errors. Both re-raise typed errors with `from exc` preserving the cause chain.

The pre-existing `except Exception: return True` at `viewdef/generator.py:398` is **not** in the diff scope (it's existing code in `_expression_uses_current_focus`). Flagging for awareness but not a finding against this feature.

---

## 5. Type safety audit

All new public functions have type annotations. The `_SQLLibraryBase` dataclass uses `Optional[str]`, `List[...]`, `Dict[str, Any]` consistently. The `DependencyResolver` type alias documents the resolver contract.

Minor: `_materialize_one` returns `None` implicitly; could be annotated `-> None`. Not a finding (consistent with the rest of the file's style).

---

## 6. Test coverage audit

| New module | Tests | Coverage |
|---|---|---|
| `sqlquery/parser.py` | 9 (smoke) | Profile dispatch, missing profile, wrong type coding, unsupported dialect, SQLView parameter rejection |
| `sqlquery/validator.py` | 2 (smoke) | Missing content, non-SQL contentType |
| `sqlquery/runner.py` | 13 (integration) | Materialization (1-level + recursive), cycle detection, parameter binding across 4 FHIR types, wrong-type/missing/unknown rejection, idempotent re-execution, dialect rejection |
| `viewdef/types.py` (§G-1) | 9 | cnl-1 url/profile/meta.profile rejection, Column.type permissiveness preserved |
| `viewdef/parser.py` (§G-2) | 5 | cnl-0 warning fires for lowercase/overlong, doesn't fire for valid |
| `viewdef/types.py` (§G-3) | 7 | Roundtrip flat-string, extension array, nested extension, meta.tag array, multiple unknown keys, known-keys exclusion, no-extra-keys default |
| `viewdef/parser.py` (§G-4) | 4 | Tag namespace warning fires for unnamespaced, doesn't fire for namespaced |
| `viewdef/test_spec_compliance.py` (§G-5) | 465 (suite) | All pass after triage fixes |

Total new tests: 56 (viewdef) + 28 (sqlquery) = **84 new tests**. Combined viewdef+fhirpath+sqlquery: **2710/2710 green**.

---

## 7. Architectural invariants (from `ARCHITECT_REVIEW.md`)

All 8 invariants preserved:

| # | Invariant | Verification |
|---|---|---|
| I-1 | One-way dep: sqlquery imports viewdef; never the reverse | `grep -rE "import\s+(fhir4ds\.)?sqlquery" fhir4ds/viewdef/` returns nothing ✓ |
| I-2 | No silent fallbacks in SQLQuery validation | All error paths raise typed `SQLError` subclasses ✓ |
| I-3 | Parameter binding via prepared statements | `runner.execute` uses `con.execute(sql_body, params)`; no interpolation ✓ |
| I-4 | `_extensions` bag preserves unknown keys verbatim | 7 roundtrip tests, including nested-complex extensions ✓ |
| I-5 | cnl-1 strictness excludes `Column.type` | Test `test_column_type_relative_uri_still_accepted` ✓ |
| I-6 | cnl-0 and §G-4 surface only as warnings | Paired tests: `validate_view_definition` warns; `parse_view_definition` doesn't raise ✓ |
| I-7 | `joins` extension runtime preserved; gate default OFF | Existing Join tests green; `_EMIT_JOINS_REQUIRES_PROFILE = False` ✓ |
| I-8 | §G-5 refresh changes only spec_tests + report + header | Confirmed via `git diff --name-only` ✓ |

---

## 8. Findings summary

| ID | Severity | Subject | Recommended action |
|---|---|---|---|
| REV-001 | LOW | `_KNOWN_LIBRARY_KEYS` lists `relatedArtifact` twice | Deduplicate; cross-check against FHIR R5 Library shape for missing keys |
| REV-002 | LOW | runner.py uses lazy imports inside methods unnecessarily | Move imports to module top; remove defensive lazy pattern |
| REV-003 | LOW | `_extensions` field uses leading underscore (unconventional for dataclass) | Consider rename to `extensions_bag` or rely on docstring for privacy signal |
| REV-004 | LOW | cnl-0 warning doesn't enforce minimum length 2 | Document the gap or extend the check; spec regex requires 2-255 chars |

None of these block release. All four are quality refinements that can land in a follow-up.

---

## 9. Handoff

Code review complete. Pipeline step `code_review` is the final step in the approved `[feature_design, feature_implementation, code_review]` pipeline. Setting `workflow: null` and `exit_reason: CLEAN` to signal clean exit. The feature is ready for release engineering at the human's discretion.

Outstanding LOW findings (REV-001 through REV-004) can be addressed in a follow-up PR or deferred indefinitely; they do not affect correctness or security.
