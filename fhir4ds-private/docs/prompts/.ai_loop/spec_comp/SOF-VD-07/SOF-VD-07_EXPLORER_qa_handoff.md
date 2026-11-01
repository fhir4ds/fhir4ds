# QA Handoff — SOF-VD-07 EXPLORER (combined battery)

## Verdict: CLEAN — 12-case combined battery PARITY OK (E half)

E1 where on nested prop (text.exists()); E2 %rowIndex with where filter —
counter follows EMITTED rows (1.2=2, 1=0 after filtering to has-kids); E3
triple path with duplicate entry ([item, item.item, item]) — union dedup; E4
repeat + unionAll same select — legal (unionAll not a row generator), NULLs
for non-matching arm; E5 empty repeat array -> ParseError; E6 repeat as string
-> ParseError.

Evidence: .temp/qa/speccomp2/sofvd07_historian_explorer_probe1.py
