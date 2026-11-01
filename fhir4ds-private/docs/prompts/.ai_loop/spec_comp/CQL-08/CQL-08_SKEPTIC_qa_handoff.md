# QA Handoff — CQL-08 SKEPTIC (Coalesce / IsNull / IsFalse / IsTrue)

## Verdict: CLEAN — zero defects (2 flags adjudicated with direct re-verification)

Coalesce basic/first-non-null/variadic; IsNull operator+function (absent field
True, id False, null is null True); IsTrue/IsFalse non-Boolean -> false doctrine
pinned. ADJUDICATIONS: (1) Coalesce-over-Boolean-field renders 'true'/'false'
STRINGS + ints as floats — population-SQL list-wrapped singleton rendering,
semantic values CORRECT; (2) String+Number Coalesce -> TranslationError is the
PINNED static type-family guard doctrine; corrected spellings verified
(numeric Coalesce -> 42.0; Quantity Coalesce(ToQuantity('junk'), 5 'mg') ->
5-mg JSON; IsTrue(Coalesce(null, true)) -> True; Coalesce(1/0, 7) -> 7.0
div-zero null feeds Coalesce).

Evidence: .temp/qa/speccomp2/cql08_skeptic_probe1.py + /tmp/opencode/cql08_adj.py
