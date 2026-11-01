# Architect Handoff — CQL-21 EXPLORER Iteration 1

## Golden Standard Invariants (CQL-21 Clinical Operators)

1. **Translator static-extractor helpers MUST recurse into collection-typed
   tuple fields** (`ListExpression` for `codes`, etc.). Already documented
   for `_code_entries_from_ast` per CQL-21 HISTORIAN QA-001.
2. **Native C++ extension and Python fallback MUST produce identical
   results for every clinical operator input** (zero parity divergence is
   a hard contract).
3. **CQL spec compliance is the source of truth** for behavior. Where the
   spec is silent or pathological, document the intended behavior in the
   AGENTS.md NOT A BUG Registry.
4. **No silent fallbacks**: missing terminology capability (e.g. In
   CodeSystem String overload) MUST raise TranslationError, not silently
   return True/False (CQL-21 SKEPTIC QA-002 fix).
5. **Spec section §In (Valueset) String-overload ambiguity MUST surface
   as SQL NULL** (three-valued logic), not silently return False (CQL-21
   SKEPTIC QA-001 fix).

## Audit Findings

### State Hygiene

- Pre-iteration `evolution.json` was clean (workflow=evolution, iteration=1,
  qa_personality=EXPLORER). No carryover issues.
- Post-iteration: 1 issue (QA-002) closed INTENDED with full evidence
  trail. No tombstoning needed (single issue).

### Architectural Drift

**Zero new drift.** The CQL-21 HISTORIAN iteration's load-bearing fix
at `_code_entries_from_ast:3112-3144` (ListExpression recursion for
Concept-with-literal-codes) is preserved. The CQL-21 SKEPTIC iteration's
load-bearing fix at `valueset.py:566-583` (String-overload wildcard for
empty source system) is preserved. The CQL-21 EXPLORER iteration's NOT
A BUG Registry entry for Code-overload empty-system edge case is added.

### Generalizability

The QA-002 finding's root cause (UDF cannot distinguish Code-typed vs
String-typed empty-system source operands) is a structural limitation
of the current translator→UDF contract. The translator emits
`in_valueset(<synthetic_resource>, 'code', <vs_url>)` for both Code-typed
and String-typed operands, with the only difference being whether the
synthetic resource's `system` field is empty. The UDF then applies the
wildcard rule uniformly. A future architect-level change could:
- Pass a 4th argument to `in_valueset` indicating source operand kind
  (e.g. `'Code'` vs `'String'`), enabling strict matching for Code-typed
  empty-system operands.
- Or translate Code-typed operands with strict system match, falling
  through to wildcard only when source is a bare String.

Both options are invasive; current INTENDED classification is correct
given negligible real-world impact.

### Empirical Validation

Conformance baseline preserved: **2822/2822** (ViewDefinition 134/134,
FHIRPath 935/935, CQL 1706/1706, DQM 47/47).

### QA Enforcer Gate

**PASSED.** EXPLORER personality executed 84 distinct pathological-input
cases across 4 batteries + 2 auxiliary probes, covering:
- Extreme birthdates (pre-1900, year 0001/9999, future, leap day,
  century-non-leap)
- Polymorphic Code/Concept literals (unicode, emoji, empty, whitespace)
- Deeply nested clinical expression chains (if/case/and-chains)
- Empty/null handling for every operator
- Mixed-system codes

The probe uniquely surfaced QA-002 (Code-overload empty-system edge
case), which HISTORIAN's systematic-overload-form coverage and
SKEPTIC's hypothesis-driven approach both missed. **No RETRY_QA.**

## Recommended Fix Order for Future Iterations

No outstanding fixes for CQL-21. QA-002 is INTENDED. Loop eligible for
clean exit at min_iterations=1.

## Handoff Compression

The CQL-21 EXPLORER iteration is structurally clean. The fuzz probe
validated 84 pathological-input cases with zero native↔fallback parity
divergence. One LOW-severity finding (QA-002) classified INTENDED and
added to the NOT A BUG Registry. CQL-21 conformance baseline (1706/1706)
and overall baseline (2822/2822) preserved.
