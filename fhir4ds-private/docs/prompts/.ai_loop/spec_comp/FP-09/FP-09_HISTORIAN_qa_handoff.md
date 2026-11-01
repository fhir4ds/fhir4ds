# QA Handoff — FP-09 HISTORIAN (§5.6.1-§5.6.5 String Search)

## Verdict: CLEAN — zero defects (17 fresh cases; 1 MISS adjudicated probe-expectation)

Normative definitions walk: indexOf 0-based first occurrence; substring spec examples
(3 -> defg, 3,2 -> de, 7,1 -> {}); startsWith/endsWith; contains; boundary rows
(indexOf self 0, substring(0) identity, char-level prefix/suffix/contains at both
ends); multi-occurrence (first only; overlapping); resource rows.

ONE MISS adjudicated: name.given.contains('John') -> [] CORRECT — given is
multi-item [John, Kim], contains is a singleton-String fn; multi-item input =
row-resilient empty on BOTH engines. The singleton form
name.given.first().contains('John') -> ['true'] verified.

Evidence: .temp/qa/speccomp2/fp09_historian_probe1.py
