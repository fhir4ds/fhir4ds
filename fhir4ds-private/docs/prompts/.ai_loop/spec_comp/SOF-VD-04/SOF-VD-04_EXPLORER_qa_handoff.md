# QA Handoff — SOF-VD-04 EXPLORER (combined battery)

## Verdict: CLEAN — adversarial composition cases E1-E6

first()-demoted typed string in forEach; where-filtered collection
(name.where(use='official').given -> ['John','Kim'] / [] / []); complex
collection HumanName JSON list per patient; full-URI type + collection;
typed boolean ('true'/'false' string renders, None absent); absent forEach
path + collection -> 0 rows for that patient. All native==fallback identical.

Evidence: .temp/qa/speccomp2/sofvd04_historian_explorer_probe1.py
