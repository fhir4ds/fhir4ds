# Engineer Handoff — SOF-VD-08 EXPLORER (iteration 1, 2026-08-23)

## Triage

| Issue | Category | Triage | Action |
|---|---|---|---|
| QA-001 backtick constants silently NULL | SPEC_VIOLATION | CONFIRMED | FIXED |

## QA-001 (HIGH) — RESOLVED

**Reproducer:** constant {name: lbl, valueString: LAB}; column path `%\`lbl\`` -> NULL; where `%\`lbl\` = 'LAB'` -> all rows dropped. Plain `%lbl` worked. (probe: .temp/qa/sof_vd08_explorer/probe1.py P6)

**Root cause:** `fhir4ds/viewdef/constants.py::iter_constant_references` recognized only `%` + identifier regex; for `%\`name\`` the identifier match failed, control fell to `i += 1`, and the next iteration hit the generic backtick skip-region branch, treating the delimited name as a literal to skip. The reference was never yielded, never substituted, and both evaluation engines folded the raw `%\`name\`` text to an empty collection silently.

**Spec:** FHIRPath spec, Environment Variables — variable names may be written as backtick-delimited identifiers; SQL-on-FHIR v2 notes — % constants are "effectively replaced by the value of the constant before the FHIRPath expression is evaluated".

**Fix (surgical, viewdef/constants.py only):**
1. `iter_constant_references` now parses `%\`name\`` (via `_skip_quoted_region`, minimal escape unescaping) and yields the name, so substitution and undefined-name validation apply.
2. `resolve_constants_in_path` normalizes builtin runtime variables to the plain `%name` spelling (`%\`rowIndex\`` -> `%rowIndex`) because the engines resolve builtins at runtime and do not accept the backtick form.
3. Undefined or non-definable (escaped, non-sql-name) backtick references now raise `ConstantResolutionError` loudly instead of silently evaluating empty. Class fix, not case-specific.

**Validation:**
- New regression class `TestBacktickConstantReferences` (7 tests) in fhir4ds/viewdef/tests/unit/test_constants.py: substitution, string-literal immunity, plain-form parity, builtin normalization, loud undefined rejection, e2e DuckDB in unionAll branch column and top-level where.
- test_constants.py + test_union.py: 128 passed.
- Full fhir4ds/viewdef pytest tree: 1208 passed.
- Master conformance gate: see final report (ViewDef 144 gate + full run recorded there).
- Native/fallback parity: fix is upstream of both engines (textual substitution); probes identical on both paths.
- Binaries unchanged (Python-only fix): fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a, repo bundle == site-packages.

## New issues discovered during fix

None.
