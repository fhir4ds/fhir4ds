# Review Feedback: FEATURE_PLAN_DRAFT v1

**Reviewer:** External (chat-based review, not the Feature Designer self-audit)
**Reviewed:** `fhir4ds-private/docs/prompts/.ai_loop/FEATURE_PLAN_DRAFT.md` (v1, pre-self-audit)
**Source gap analysis:** `fhir4ds-private/docs/plans/SQL_ON_FHIR_V2_GAP_ANALYSIS.md`
**Date:** 2026-08-11
**Purpose:** Feed into Step 4 (Refine the FDD v2) of the Feature Designer workflow. The Feature Designer should address each finding in the refined plan or push back with reasoning.

---

## Overall Assessment

The plan is strong. Coverage is complete — every gap from the source analysis (§G-1 through §G-5, §M-1, §M-2, §E-1) has a corresponding step or scope gate. Sequencing is correct (§G-5 lands first as a measurement blocker). The §M-2 scope gate is well-framed. Definition of Done is concrete and testable.

The findings below are quality improvements and ambiguity resolutions, not fundamental design objections. None block the APPROVAL gate by themselves, but findings **#1, #3, #4, #5** will distort or block implementation if not resolved before Step 7 (§M-1 SQLQuery) begins.

---

## High Priority (resolve before Step 7)

### 1. Step 4 §G-3 extension bag: depth ambiguity

The plan states: *"for every unknown top-level key in the input dict, store it in `_extensions` verbatim."* FHIR DomainResource fields are nested — `text.div`, `meta.security[]`, `contained[]`. Roundtripping `text` needs the whole nested structure preserved, not just the top-level key.

**Required clarification:** state explicitly whether the extension bag is deep-copy-verbatim at the value level (preserves any nested structure) or whether it only captures flat top-level keys. Recommended wording: *"Deep-copy each unknown top-level key's value verbatim. Do not flatten, do not recurse into known vs unknown sub-keys — the entire JSON value (including any nested objects or arrays) is preserved as-is."*

Add a roundtrip unit test that includes a `text` key with a nested `div` and assert byte-for-byte survival of the inner structure, not just the outer key.

### 2. Step 4 §G-3 dataclass field naming

A leading underscore on a dataclass field (`_extensions`) is fragile. `dataclass(_extensions=dict)` requires `_extensions=` as a kwarg at construction time, which is awkward for direct callers and surprising for IDE autocomplete.

**Recommended fix:** rename to `extra_fields` (or `extensions_bag`) without the underscore, and configure as:
```python
extra_fields: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)
```
The `repr=False, compare=False` flags keep it out of equality and repr semantics so it doesn't break existing dataclass equality assumptions in tests.

### 3. Step 1 §G-5 brittle assertion

`fhir4ds/viewdef/tests/test_spec_compliance.py` line 630 hard-codes:
```python
assert len(files) == 22
assert len(all_tests) == 134
```

After the §G-5 refresh, the second assertion will fail at the count check before any real test runs. The plan must explicitly call out this line as a must-edit during Step 1, or the engineer will hit a confusing test-runner failure that looks unrelated to the actual refresh work.

**Recommended fix in Step 1 task list:** add a sub-task — *"Update `test_spec_compliance.py:630` to reflect new totals (22 files unchanged, 134 → 144 tests). Consider replacing the strict equality with a `>= 134` floor plus a logged actual count, so the next suite growth does not break the runner."*

### 4. Step 7 §M-1 parameter type mapping is undefined

The plan says *"coerce each parameter value from its FHIR type to the corresponding DuckDB type"* without enumerating the mapping. The hard cases are `Coding`, `CodeableConcept`, `Quantity`, `Period` — DuckDB has no native types for these, and naive coercion will silently corrupt data.

**Required clarification:** pick one of the following and document it in Step 7d:

- **Option A (recommended):** MVP allows primitive parameters only — `integer`, `integer64`, `string`, `code`, `decimal`, `boolean`, `date`, `dateTime`, `time`, `instant`, `uri`, `url`, `uuid`, `id`, `canonical`, `oid`, `markdown`, `base64Binary`, `positiveInt`, `unsignedInt`. Reject complex types (`Coding`, `CodeableConcept`, `Quantity`, `Period`, etc.) with a typed `SQLQueryParameterError`. This covers the spec's main use cases (parameterized WHERE clauses, time bounds, code filters) and defers the hard structural modeling work.
- **Option B:** JSON-encode complex types as `VARCHAR` (round-trippable but opaque to SQL). Document the encoding explicitly.

Option A is the lower-risk MVP. Either way, the supported type list and the rejection behavior for unsupported types must be in the plan.

### 5. Step 7 §M-1 typed error hierarchy not enumerated

Only `SQLQueryCycleError` is named. Step 7d references errors informally ("raise `SQLQueryDialectError`", "typed error"). A reader cannot infer the full hierarchy or how it relates to the existing `fhir4ds/viewdef/errors.py` root.

**Required clarification:** enumerate the error hierarchy in Step 7a or 7d. At minimum:

| Error | Raised when |
|---|---|
| `SQLError` (root) | Base class for all sqlquery errors |
| `SQLQueryParseError` | Library JSON does not match Library shape |
| `SQLQueryProfileError` | `meta.profile` missing or wrong |
| `SQLQueryValidationError` | Profile invariant violation (e.g., `sql-must-be-sql-expressions`) |
| `SQLQueryResolutionError` | A `relatedArtifact.resource` canonical cannot be resolved |
| `SQLQueryMaterializationError` | A dependency ViewDefinition fails to generate |
| `SQLQueryDialectError` | No `content[]` entry matches a supported dialect |
| `SQLQueryParameterError` | Missing required parameter, wrong type, or unsupported complex type |
| `SQLQueryCycleError` | Dependency graph has a cycle |

Decide whether `SQLError` inherits from the existing `SQLOnFHIRError` (root in `viewdef/errors.py`) or is independent. Recommendation: inherit — it lets consumers catch the existing root and get sqlquery errors for free.

### 6. Step 7 §M-1 content-type selection precedence

Plan says *"Prefer `application/sql;dialect=duckdb`; fall back to `application/sql`."* Unclear what happens when a SQLQuery has multiple matching dialect-specific contents (e.g., both `application/sql;dialect=postgres` and `application/sql;dialect=duckdb`).

**Required clarification:** explicitly specify the precedence algorithm:

1. Exact match on `application/sql;dialect=duckdb` wins.
2. If none, fall back to bare `application/sql`.
3. If multiple entries match at the same precedence level, first-declared wins.
4. If no entry matches, raise `SQLQueryDialectError` listing the supported dialects.

---

## Medium Priority (resolve during implementation)

### 7. Version target should recommend, not just ask

Open Question #3 punts the version-bump decision to the human. Adding a new public package (`fhir4ds/sqlquery/`) plus new validator and warning surfaces on `viewdef` is unambiguously a SemVer minor bump. Staying at `0.0.x` would mislead consumers about API stability of the new module.

**Recommended default:** `0.1.0`. Note in Open Question #3 that the recommendation is `0.1.0` unless the human explicitly wants to keep `0.0.x` for staging reasons.

### 8. Rollback strategy if Step 7 overruns

Definition of Done lumps Step 7 in with the rest. But Steps 1–6 + 8 are independently shippable — they deliver the ViewDefinition-layer compliance work without depending on SQLQuery.

**Required clarification:** make explicit in §1 (Definition of Done) and §8 (Estimated Schedule) that a partial feature landing — Steps 1–6 + Step 8, with Step 7 deferred to a follow-on directive — is a valid APPROVAL-gate outcome if Step 7 estimation tightens upward during implementation. This avoids forcing an all-or-nothing bet on the 1.5-week SQLQuery MVP.

### 9. Step 7 risk: latent bugs in `viewdef/generator.py`

No consumer has ever tried to materialize a ViewDefinition as a DuckDB `CREATE VIEW`. The first SQLQuery integration test may surface generator bugs that the existing 1,061-test internal suite has never exercised (e.g., generator output that works as a standalone `SELECT` but breaks when wrapped as a view definition).

**Required clarification:** acknowledge this risk in Step 7 and budget 1–2 contingency iterations in the §8 schedule. Note that the §G-5 spec suite refresh in Step 1 is the first line of defense — if the new `repeat.json` tests pass cleanly, generator risk is lower; if they surface bugs, generator risk is higher and Step 7 should expect to absorb some of that.

### 10. Step 3 §G-2 cnl-0 single-character edge case

The cnl-0 regex `^[A-Z]([A-Za-z0-9_]){1,254}$` requires ≥ 2 characters. The plan checks `not vd.name[0].isupper()` and `len(vd.name) > 255` but not `len(vd.name) < 2`. A name like `"A"` passes `sql-name` but violates cnl-0.

**Recommended fix in Step 3 task list:** add the third condition — `len(vd.name) < 2` — to the warning trigger. Add a unit test asserting the warning fires for `name='A'`.

---

## Low Priority (quality improvements)

### 11. Location of `joins` extension disclosure doc

Step 6 says the disclosure lands *"in `fhir4ds-private/docs/` (location TBD by writer)."* The docs dir has subdirs (`plans`, `prompts`, `bug-fixes`, `marketing`, `notebooks`). 

**Suggested concrete path:** `fhir4ds-private/docs/extensions/JOINS_EXTENSION.md`. This establishes a home for future fhir4ds-specific extension disclosures (not just `joins`).

### 12. Gap analysis disposition post-feature

Once the FEATURE plan ships, what happens to `SQL_ON_FHIR_V2_GAP_ANALYSIS.md`? Options:
- Mark as superseded (add a banner pointing to the FEATURE plan and the post-feature conformance report)
- Keep as historical context (no changes)

**Suggested:** mark as superseded in Step 8. The gap analysis was the input; the FEATURE plan and the post-implementation conformance report are the durable artifacts. Without a supersession marker, future readers may rely on stale gap claims.

### 13. Step 1 — does fhir4ds handle `QuestionnaireResponse`?

The 12 new `repeat.json` tests likely include `QuestionnaireResponse` (the spec explicitly cites QR items as the canonical `repeat` use case). If fhir4ds has a gap in QR resource-type support, those tests may fail for reasons unrelated to `repeat` semantics — confusing the triage.

**Recommended:** a quick capability check during Step 1 task 3 (the initial run). If QR-specific failures appear, classify them as `resource-support` rather than `repeat-semantics` so the triage stays clean.

---

## Findings Not Addressed in v1 (Confirmed)

For completeness, these v1 plan elements were reviewed and found correct — no changes needed:

- Sequencing: §G-5 first as measurement blocker — correct.
- §M-2 scope gate (Gate A, library-only default) — correct framing.
- Cycle detection algorithm in Step 7d — correct.
- SQL injection analysis — honest about the author-SQL threat model.
- Non-regression constraints (§6) — complete and correct.
- Out-of-scope list (§7) — correctly bounds the feature.
- Open Questions (§9) — the right questions, with the exception of #3 (see finding #7 above).

---

## Summary

| Severity | Count | Action |
|---|---|---|
| High | 6 | Resolve in v2 plan before Step 7 begins |
| Medium | 4 | Resolve during implementation; do not block APPROVAL |
| Low | 3 | Quality improvements; address opportunistically |

The v1 plan is approvable after the High-priority findings are addressed in v2. The Medium and Low findings can be tracked as issues during implementation.
