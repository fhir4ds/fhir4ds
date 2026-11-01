# QA Handoff — CQL-01 SKEPTIC

Scope: CQL primitive types Any, Boolean, Integer, Decimal, String, and Long (CQL 1.5 trial-use). Used fresh source inspection, CQL 1.5.3 spec pages, official local CQL fixtures, and `.temp/qa/cql01_probe.py`; no spec_comp/archive artifacts were used.

Findings:
- `CQL01-QA-001` HIGH: `5 is Any` translated to JSON resource type extraction and failed in DuckDB. Spec says System.Any is the maximal supertype, so every non-null value is ultimately Any.
- `CQL01-QA-002` HIGH: signed Integer minimum was rejected and Long overflow was accepted; Decimal max-precision rendering also passed through Python float scientific notation.
- `CQL01-QA-003` MEDIUM: public DuckDB `ToInteger` rounded/errored through `CAST`, and direct Python conversion checks accepted decimal-looking integer strings contrary to the CQL integer string grammar.

Spec anchors:
- CQL 1.5.3 Developer's Guide §3.1.3 Literals, §3.4.1 System-Defined Types, and §3.4 Type Testing.
- CQL 1.5.3 Reference §ToInteger, §ConvertsToInteger, and §ToLong.

Fresh probe log:
- `.temp/qa/cql01_probe.log` captured failing behavior.
- `.temp/qa/cql01_probe_after3.log` captured fixed behavior across translator rendering and public native/fallback DuckDB CQL surfaces.
