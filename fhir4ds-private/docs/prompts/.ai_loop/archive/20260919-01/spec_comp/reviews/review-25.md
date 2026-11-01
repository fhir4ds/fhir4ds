# Code Review Findings — Spec-Compliance Campaign Milestone #5 (CQL-01..CQL-05)

**Date:** 2026-08-20
**Reviewer:** Code Reviewer role (milestone `code_review` workflow, fifth launch)
**Scope:** Uncommitted working-tree diff vs `db1e4164` (dev), delta since milestone #4 (review-20.md + milestone-4 reconciliation): CQL-01..CQL-05 chunk fixes (exact-Decimal arithmetic incl. cqlDivide UDF + typed Sum/Avg + cql_type-keyed casts; clinical-type equivalence Code/Concept ~ keys, structured folding, VS/CS alias unwrap; temporal strict literal lexing, component accessors, sub-second precision, MinValue/MaxValue folds; structural ops First/Last over retrieves, Children/Descendants UNNEST, FHIR_TYPE_TO_CQL_TYPE map, as-cast alias projections; parser not-precedence; placeholder ORDER BY traversal; add_alias restoration), native cql extension (quantity.cpp UCUM validity guards, cql_extension.cpp CompareTemporal, rebuilt binary), and the CQL-05 QA-103 DQM gate break/repair.

## Status of prior findings

- **REV-001 (LOW, OPEN)** — unguarded `std::stoi` family in `fhirpathSplitUnitTerm` (evaluator.cpp ~2151). Unreachable from literals; hardening only. Unchanged.
- **REV-002 (MEDIUM, OPEN)** — hand-maintained metadata duplicated across engines. No new duplications added this period; `FHIR_TYPE_TO_CQL_TYPE` (inference.py:41) is a new hand-maintained FHIR-primitive→CQL-type map, but it encodes CQL 1.5 spec-level system-type mapping (not resource/profile knowledge) and is acceptable; note as same-family drift surface only.
- **REV-003 (LOW, OPEN)** — unrelated untracked files still in tree (`conformance/architecture/`, `fhir4ds/dqm/AGENTS.md`). Unchanged.
- **REV-004 (LOW, OPEN)** — `exactDecimalRatioText` (evaluator.cpp:2606) now has input bounds (`digits.size() > 25 || scale > 20` reject) which bound the multiplication magnitude; still no explicit 128-bit budget guard. Keep OPEN (hardening).
- **REV-005 (LOW, OPEN)** — `_compile_regex` (engine/invocations/strings.py:151) still passes patterns verbatim to `re.compile`; mid-pattern inline flags deprecation unchanged.
- **REV-006 (HIGH, RESOLVED/verified)** — `operators.py::membership` FHIRPathError raise restored ("in requires the left operand..." present); integration parity at milestone-4 reconciliation: 765 passed.
- **REV-007 (MEDIUM, RESOLVED/verified)** — lost evaluator.cpp fixes re-landed; symbol audit this review confirms (see below).

## Clobber-hazard spot check (FP-11..FP-20 + CQL-01..05 symbols)

evaluator.cpp (grep -a): `leastPrecisionDecimalPlaces`, `powerDecimalExactText`, `expandScientificToFixed`, `frac_digits`, `decimalFactorRatio`, `exactDecimalRatioText` all present (19 combined hits); `!explicit_namespace` isType guard present (3 sites); `fhirFieldType` extension entries present; operators.py membership raise present. CQL side: `cqlDivide` UDF (macros/math.py), `FHIR_TYPE_TO_CQL_TYPE` (inference.py), `_validate_datetime_literal` (lexer.py:1164), `same_code_unit_valid_for_compare` + UCUM prefix guards (quantity.cpp), `CompareTemporal`/`CompareTemporalComponents` (cql_extension.cpp:2876+), placeholder ORDER BY traversal (placeholder.py:304), add_alias row-shaped registration (_query.py:4525). **No lost hunks detected.** CQL extension binary fresh (build 01:31 > cql_extension.cpp 01:19 > quantity.cpp 00:42) and md5 `10eaecdb...` matched across repo bundle and site-packages; no ~/.duckdb cache copies.

## DQM gate repair (CQL-05 QA-103) soundness

Structurally sound, not a patch-over:
- Root cause 1 (add_alias drop): the fix restores `add_alias(alias, table_alias=alias, cte_name=provisional_cte_name)` at the row-shaped `inner_query.where` branch (_query.py:4513-4525) with a comment explaining correlated-reference semantics, while the QA-101 value-projection branch (lines 4527-4569) remains intact — both behaviors coexist correctly rather than one papering over the other.
- Root cause 2: `resolve_placeholders` now traverses `SQLSelect.order_by` preserving `(expr, direction)` tuples (placeholder.py:304, 434) — general AST traversal fix, not case-specific.
- The three defensive narrowings (`_narrow_to_resource_column`, `_translate_identifier` scalar narrowing, `_ensure_resource_to_interval`) only affect previously-invalid 2-column shapes.
- Evidence: dqm_report.json 48/48 measures at 100.0% accuracy; conformance master gate 2832/2832 per chunk handoffs; spot test run this review: test_structural_type_parity + test_clinical_type_parity 46/46 passed in 112s.

## New findings

**None.** No SQL-injection vectors (f-string `execute` hits are test files asserting on generated SQL, not runtime interpolation of user input), no new error swallowing (single `except Exception` at _functions.py aggregate typing is a scoped conservative static-inference fallback, not execution masking), no SQLRaw/to_sql misuse in runtime paths (hits are test assertions), no IG/model-specific hardcoding in generic logic (Code/Concept/Quantity/VS handling is CQL-spec-driven; no measure IDs, patient IDs, or ValueSet content embedded).

## Overall assessment

The CQL-01..CQL-05 delta is clean and spec-grounded; the QA-103 DQM repair addresses the true root causes with general fixes; the milestone-4 clobber reconciliation has held (no new lost hunks). The tree carries five open LOW/MEDIUM hardening/debt items (REV-001..005) and a known residual of 7 FHIRPath integration parity failures (2 std::regex named-group limits + 5 temporal-edge fallback expectations) outside the conformance gate. No blocker for the next pipeline step.
