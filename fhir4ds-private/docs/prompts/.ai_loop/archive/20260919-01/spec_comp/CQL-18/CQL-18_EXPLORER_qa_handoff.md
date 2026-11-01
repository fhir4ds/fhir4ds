# qa_handoff.md — CQL-18 EXPLORER launch (2026-08-22)

Persona: EXPLORER (fuzzer/abuser). Chunk CQL-18: CQL 1.5 List Operators Part 1.
Spec verified directly against CQL reference Appendix B (List Operators) fetched
from cql.hl7.org (semantics identical to 1.5 for these operators).

## Method
Per-define bisected population-SQL probes on python-registered DuckDB
(`.temp/qa/cql18e3_2026_08_22/per_def.py`, `followup.py`, `probe.py`).
Multi-patient resources (P1: Observation with 2 components 8480-6/8462-4;
P2: Observation with component 8867-4) for correlation checks. Full-library
3-mode parity (python/native/no_python) attempted; big library blocked by
QA-002 crash; smaller parity confirmed identical across modes for all passing
cases (probe.py mode_diffs == [] before the chained-define crash).

## Verified clean (no issue)
Contains/In null-element and null-list semantics; Distinct nulls-collapse
({null,null}->{null}), int/decimal collapse ({1,1.0,2,2.0}->{1.0,2.0}), tuples;
Equal/Equivalent on tuples, nulls-equal, length mismatch; Concept-list
equivalence by code intersection ignoring display; IndexOf duplicates (first
occurrence), not-found -1, null list null; Except/Intersect set semantics with
duplicates ({1,3,3,5} except {1} -> {3,5}; {3,3,5,7} intersect {3,5,5} ->
{3,5}) and null-element participation; Except null-right-as-empty / null-left
null; Intersect null-either null; Exists {null}->false, empty/null-list false;
Count null-only 0; Flatten depth-2 mixed with empty inner ({ } dropped, one
level only); First/Last single-element and empty; single-level alias First /
alias-of-First / IndexOf / Count / Distinct / Except / Flatten; properly
includes/includes null-element singleton (true); Obs.code.coding.code and
inline Count(Obs.component.code.coding.code) per-patient values correct
(P1=2, P2=1) — per-patient lists stay isolated.

## Issues (all logged in evolution.json)
- QA-001 CRITICAL — define-alias of deep multi-valued navigation over a
  retrieve define (`define CC: Obs.component.code.coding.code`) generates
  invalid population SQL (GROUP BY binder error); ALL list-operator consumers
  of the alias crash. Inline equivalent works. HISTORIAN's QA-001 fix covered
  single-segment 0..* (O.component) only.
- QA-002 HIGH — inline chained list operators crash: `(A except B) includes e`,
  `X except distinct Y`, `(A intersect B) includes e`, `A includes distinct B`,
  `(Flatten(...)) includes e` -> Binder/Parser errors. Define-intermediate
  workaround works.
- QA-003 HIGH — Includes/IncludedIn null semantics: `{null,1} includes null` ->
  false (spec true); `null included in {1,null}` -> false (spec true);
  list-list null operand -> false (spec null). contains/in handle these
  correctly — includes/included-in diverge from their spec-defined synonyms.
- QA-004 HIGH — `define A2: distinct A_Lit; define R: First(A2)` returns the
  whole list [10,20,30] instead of 10 (two-level aliasing defeats the
  First/Last pre-translate).
- QA-005 MEDIUM — heterogeneous list literal {1, 1.0, 'x', null} fails at
  DuckDB execution (ConversionException) instead of a typed CQL
  TranslationError (no common element type).

## Notes for Remediation
- Suspect areas: `fhir4ds/cql/translator/expressions/_functions.py`
  (_promote_fhirpath_text_list, _translate_flatten_pre, includes dispatch),
  definition-meta `stores_list_value` handling in expressions/__init__.py and
  correlation.py. QA-001 smells like the aggregate pre-translate wrapping the
  deep navigation subquery without re-correlating patient_id; QA-004 like
  First pre-translate not re-entering when operand is an alias whose
  DefinitionMeta lacks stores_list_value but resolves to a list.
