# QA Handoff - CQL-11 HISTORIAN

Scope: systematic CQL Arithmetic Operators Part 2 walk-through against the CQL 1.5.3 reference and the local official XML tests. I exercised translated execution, native-loaded DuckDB registration, forced Python fallback registration, and no-Python/C++-only runtime surfaces.

Confirmed seven findings. The highest-risk issues are numeric boundary handling for `Negate`, decimal min/max predecessor/successor overflow, and dynamic FHIR choice arithmetic for `div`, `Power`/`^`, `Round`, and `Truncate`. Additional public-surface issues cover static DateTime literal boundary detection, C++-only invalid Time predecessor handling, Python `mathPower` overflow resilience, and DateTime precision with numeric timezone offsets.

Round negative ties are not logged as a defect in this pass: the published CQL 1.5.3 reference text says `Round(-0.5)` is `-1`, but the local official XML conformance suite expects `0.0`, and current implementation follows the XML to preserve 1706/1706 conformance.

Primary reproducer: `.temp/qa/cql11_historian_probe.py`, with supplemental direct probes captured in terminal output during the HISTORIAN pass.
