# QA Handoff — FP-08 SKEPTIC (§5.5.7-§5.5.9 Quantity/String/Time Conversion)

## Verdict: CLEAN — zero defects (49 fresh dual-path cases: probe1 30 + probe2 19)

toQuantity (string-quoted/unit-1/Boolean/passthrough; unit-conversion examples
1 year→12 month, 1 month→30 day, 1 kg→1000 g, 1 cm→10 mm; same-unit identity;
incompatible-unit empty per MAY clause); convertsToQuantity (valid/junk; with-unit
forms true/false); toString (integer/decimal-.0/boolean/string/date/time T-less/
quantity-quoted/calendar-bare rows; convertsToString); toTime (string forms incl.
bare '14:30' WITHOUT T-prefix — fixtures tests-fhir-r4.xml:351-352
testStringHourConvertsToTime/testStringMinuteConvertsToTime pin bare forms TRUE,
adjudicating my [false] expectation as a probe artifact; T-forms; full precision;
bad-minute rejection); multi-item/empty propagation row-resilient both engines;
typed-input edges (@2015.toQuantity empty, @T14:30.toString → '14:30');
deep compositions (qty→toString round-trip, iif-over-converts, value/.unit
extraction, toString-feeds-equality).

Evidence: .temp/qa/speccomp2/fp08_skeptic_probe{1,2}.py
