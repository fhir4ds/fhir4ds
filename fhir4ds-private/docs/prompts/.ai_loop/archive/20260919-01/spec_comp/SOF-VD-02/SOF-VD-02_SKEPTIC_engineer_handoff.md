# Engineer Handoff — SOF-VD-02 (SKEPTIC), iteration 1

## Triage
| Issue | Category | Verdict |
|---|---|---|
| QA-001 MEDIUM: integer64 constants >int32 silently evaluate empty | SPEC_VIOLATION (silent wrong results; FHIRPath Integer literal is 32-bit) | RESOLVED |

## Fix
- **Root cause**: `fhir4ds/viewdef/constants.py:resolve_constant` substituted any integer64 value as a bare FHIRPath integer literal; both engines (native + fallback) fold out-of-int32 literals to the empty collection with no error, producing silent NULL/empty results in every context (columns, where filters).
- **Spec**: SQL-on-FIR v2 IG constant.value[x] includes valueInteger64; FHIRPath §Literals — Integer literals are 32-bit signed. Substituting an unrepresentable value yields an invalid expression → must fail explicitly, not silently.
- **Change**: `resolve_constant` raises `ConstantResolutionError` (typed, carries constant_name/constant_type) for integer64 values outside -2147483648..2147483647. In-range integer64 still substitutes as a numeric literal. `SQLGenerator.generate` surfaces the error end-to-end (verified).
- **Tests**: `fhir4ds/viewdef/tests/unit/test_constants.py` — new `TestInteger64Range` (6 tests); updated `test_resolve_integer64_string_as_numeric_literal` which had pinned the silent out-of-range shape.

## Validation (fresh, FINAL tree)
- viewdef pytest: 1159/1159 passed.
- Master gate: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2832/2832.
- No native changes; fhirpath extension md5 57d0634b6ee6eddee9fc06a1355bef5a matched repo bundle and site-packages.

## Not-a-bug registrations (from QA probes, recorded in AGENTS.md)
- Temporal constants substituted as quoted strings (not @-literals) — engine coerces with identical semantics to native literals; fixtures pass.
- `.hour` on time constants empty — engine lacks time-literal `.hour` natively too (FP-chunk scope).
- Unknown extra fields inside constant items tolerated — consistent with §G-3 unknown-field roundtrip preservation.
