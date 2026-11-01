# QA Handoff — CQL-18 HISTORIAN+EXPLORER combined battery

## Verdict: CLEAN — 18/18 fresh dynamic-source cases, 0 parity diffs

Single-lib combined battery (.temp/qa/speccomp2/cql18_historian_explorer_probe1.py)
exercising the list operators over DYNAMIC resource paths (the main-tree CQL-18
dynamic-promotion doctrine): Patient.name.given contains/in/exists/Count/First/
IndexOf/distinct over the 2-element given list; flatten over a query source
(Count(flatten((from [Patient] P return P.name.given))) = 2 — the full-list
projection, not fhirpath_text truncation); union/except/intersect with literals
(3/1/1); list = and ~ self-equality True (order-wise semantics at dynamic
surface); if..then..else over contains ('has-kim'); null in dynamic list → False
(the pinned null-in-false doctrine at the dynamic surface).

Values (native == fallback identical):
[('p1', True, True, True, 2, 'John', 2, True, 1, False, 2, 3, True, True,
'has-kim', 1, 1, 'John', False)]

One harness fix mid-run: iif() is FHIRPath-ism (CatalogException) — CQL spelling
is if..then..else (documented doctrine, reconfirmed at the dynamic surface).

HISTORIAN angles: normative walk over dynamic-path list semantics per CQL 1.5
Appendix B list operators. EXPLORER angles: adversarial compositions (union with
extra literal crossing the promotion boundary; except/intersect on dynamic lists;
if..then..else over membership; null-element membership).
