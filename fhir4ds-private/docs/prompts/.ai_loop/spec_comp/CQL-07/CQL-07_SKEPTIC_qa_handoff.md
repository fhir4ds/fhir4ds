# QA Handoff — CQL-07 SKEPTIC (To* conversion functions)

## Verdict: CLEAN — 18+3 fresh dual-path cases, 0 parity diffs (2 flags adjudicated)

ToBoolean ('true'/'YES' True; 'vrai' -> False — RETURNS FALSE not null for
unconvertible strings, both engines identical; my None expectation was the miss);
ToInteger ('42'=42, '4.0' None decimal-string rejection); ToLong (int64-max ok);
ToDecimal ('3.14' -> Decimal scale-8); ToDate ('2024-06-15' ok, '2024-13-01' None);
ToDateTime (+05:00 offset preserved); ToTime ('T14:30:00' + bare '14:30' -> T-forms);
ToString (5->'5', true->'true'); ToQuantity (bare-calendar '5 years' ok JSON,
bare-UCUM '5 mg' None per pinned doctrine); null propagation (ToInteger(null) None).
Adjudicated: ToQuantity('5 ''mg''') quoted-string needs CQL doubled-quote escaping
(direct chr-built form was a ParseError both engines — probe spelling); verified
via /tmp/opencode/cql07_adj.py: quoted form + ToString round-trip "5 'mg'" BOTH ok.

Evidence: .temp/qa/speccomp2/cql07_skeptic_probe1.py + /tmp/opencode/cql07_adj.py
