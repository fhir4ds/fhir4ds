# QA Handoff — CQL-02 (CQL 1.5 Types — Clinical), iteration 1, SKEPTIC (fresh launch, 2026-08-19)

## Method
Execution-level probing (translate_cql per-definition SELECT + translate_library_to_sql
full pipeline) on BOTH Python fallback and native C++ registrations, spec-grounded
against local CQL 1.5 spec (09-b-cqlreference.md Code/CodeSystem/Concept/ToConcept/
ToString/Clinical Operators Equal+Equivalent, 05-languagesemantics.md structured types
and 1.5 Vocabulary version notes). Probe: `.temp/qa/cql02_skeptic_fresh_probe.py`
(31 definition-level cases, 0 native-vs-fallback parity diffs — all findings are
spec divergences shared by both backends).

## Verified clean (no action)
- Code tuple accessors on literals and named codes (.code/.system/.display/.version)
- Concept literal display accessor; Concept { codes: { Code{...} } } with inline codes
- Code equality (=) tuple semantics: identical→true, display/version differ→false,
  different components specified→null, null→null; Concept equality display-sensitive
- Equivalence ignores display/version; both-null-literals→true; Code~Concept
  intersection semantics incl. empty/null concept cases (totality)
- ToConcept(Code) display propagation; ToConcept(null as Code)→null;
  ToConcept(List<Code>) structured codes JSON, no display; ToConcept({})→empty codes
- ToString(Code/Concept)→null (no overload, CQL-07 doctrine)
- codesystem/valueset declarations incl. codesystems override clause; `in` codesystem
  static membership incl. null→false; Vocabulary is/as hierarchy
- No ToCode built-in in CQL 1.5 (FHIRHelpers-only) — nothing to test

## Issues (see evolution.json)
- QA-001 HIGH: Code/Concept `~` is case-SENSITIVE on code+system; spec defines it via
  string equivalence (case-insensitive, whitespace-normalized). Root:
  `_code_key` in `_operators.py::_translate_equivalence_op`.
- QA-002 HIGH: `Concept { codes: { "NamedCode", ... } }` double-serializes named codes
  as strings inside the codes JSON list; Count((...).codes)=1 for 2 codes. Root:
  generic instance path `_lists.py::_translate_instance_expression`.
- QA-003 HIGH: `.codes` accessor on Concept values returns ONE code, not List<Code>;
  Count(concept.codes) returns 0. Root: accessor lowers to fhirpath_text first-element.
- QA-004 HIGH: top-level define of a static clinical literal referenced by alias from
  another definition emits a patient-correlated subquery against a patient-id-less
  CTE → Binder error end-to-end (also pre-existing for String/Integer literal defines;
  same root cause family). Equivalence paths fold correctly already.
- QA-005 LOW (INTENDED GAP): static Code-in-CodeSystem membership is structural
  (system match, no expansion) — intended absent terminology data.

## Notes for FIX
- All four HIGHs reproduce identically on Python fallback and native C++ → fix at the
  translator layer (no extension rebuild needed unless evaluator.cpp also has these
  paths; check `ToConceptFromList` SQL shape for QA-003).
- QA-004 fix should follow the AGENTS.md CQL-02 EXPLORER doctrine: inline statically
  known clinical literal definitions at reference sites (no standalone CTE lookup);
  consider the generic scalar-literal case, but keep the fix surgical to clinical
  literals if the String/Integer case risks wider blast radius (log as followup).
