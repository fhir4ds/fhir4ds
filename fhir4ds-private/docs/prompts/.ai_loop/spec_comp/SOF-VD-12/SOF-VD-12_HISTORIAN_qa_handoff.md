# QA Handoff — SOF-VD-12 HISTORIAN/EXPLORER (combined battery)

## Verdict: CLEAN — 22 checks (flagged=0)

H1 full canonical metadata round-trip byte-fidelity (url/version/name/title/
status/description/id/meta.versionId/meta.tag/publisher/purpose/copyright/
experimental/useContext); H2 to_dict -> parse -> to_dict identity; H3 XML
input -> typed ParseError ('XML ViewDefinition parsing is not supported');
H4 Shareable+Tabular profiles together. E1 empty-string canonical in
meta.profile rejected; E2 numeric constants (valueDecimal/valueInteger)
round-trip; E3 official-style examples parse+generate; E4 contained +
extension retention.

Evidence: .temp/qa/speccomp2/sofvd12_historian_explorer_probe1.py
