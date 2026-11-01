# QA Handoff - CQL-15 SKEPTIC

Scope: CQL Interval Operators Part 1, with direct public DuckDB helper probes, translated scalar CQL execution, forced Python fallback, native-loaded registration, and no-Python C++ extension checks.

Spec anchor: CQL interval `start` and `end` operators use the effective interval boundaries. Open low boundaries start at the successor of the excluded low bound; open high boundaries end at the predecessor of the excluded high bound.

Hypotheses probed:
- Open interval boundaries may leak raw excluded endpoints through `intervalStart`/`intervalEnd`.
- Precision helper parse failures may diverge between forced Python fallback and no-Python C++ surfaces.
- Translated scalar `start of`/`end of` may inherit public helper boundary bugs.
- Date and DateTime day precision open boundaries may step at the wrong granularity.
- Existing parity tests may cover closed happy paths but miss open-bound direct helpers.

Finding:
- `QA-001` HIGH: `intervalStart` and `intervalEnd` return raw excluded open boundaries instead of effective successor/predecessor boundaries. Reproduced in forced Python fallback, native-loaded registration, no-Python C++ direct extension, and translated scalar CQL. Examples: `intervalStart({"low":1,"high":5,"lowClosed":false})` returned `1` instead of `2`; `intervalEnd({"low":"2024-01-01","high":"2024-01-31","highClosed":false})` returned `2024-01-31` instead of `2024-01-30`.

Focused checks run:
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py -q` -> 4 passed before remediation.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py -q -k 'browser_interval or required_functions'` -> 2 passed before remediation.
- `.temp/qa/cql15_skeptic_probe.py` captured the open-bound failures and a Python-vs-C++ malformed precise-helper difference.
