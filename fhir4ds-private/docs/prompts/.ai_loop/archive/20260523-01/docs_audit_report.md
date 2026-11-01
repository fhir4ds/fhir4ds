# Docs Audit Report

Target version: `0.0.6`

## 1. Notebook Execution Status

- `docs/notebooks/cql.ipynb`: Pass. Executed in place with no error outputs.
- `docs/notebooks/dqm.ipynb`: Pass. Executed in place with no error outputs.
- `docs/notebooks/fhirpath.ipynb`: Pass. Executed in place with no error outputs.
- `docs/notebooks/viewdef.ipynb`: Pass. Executed in place with no error outputs.

Notebook install cells now use the `0.0.6` target version with a local `dist/` wheel fallback:

```text
%pip install -q --find-links ../../dist fhir4ds-v2==0.0.6
%pip install -q --find-links ../../dist "fhir4ds-v2[measures]==0.0.6"
```

## 2. Stale Data Log

Fixed:
- `docs/notebooks/cql.ipynb`: updated install pin from `0.0.5` to `0.0.6`; execution refreshed old `0.0.3` captured output.
- `docs/notebooks/dqm.ipynb`: updated install pin from `0.0.5` to `0.0.6`; execution refreshed old `0.0.3` captured output.
- `docs/notebooks/fhirpath.ipynb`: updated install pin from `0.0.5` to `0.0.6`; execution refreshed old `0.0.3` captured output.
- `docs/notebooks/viewdef.ipynb`: updated install pin from `0.0.5` to `0.0.6`; execution refreshed old `0.0.3` captured output.
- `web/website/docs/getting-started/releases.md`: expanded the `0.0.6` release notes to match the actual release loop, including conformance counts, HEDIS/DQM fixes, reference resolution, stratifiers, and DuckDB `1.5.2` packaging safety.

Verified:
- `npm run build` in `web/website` passed after docs edits, covering Docusaurus internal link validation.
- Placeholder scan found no active `[PLACEHOLDER]` sections in `docs/` or `web/website/docs/`.
- Conformance claims match the release gate: ViewDefinition `134/134`, FHIRPath `935/935`, CQL `1706/1706`, DQM `47/47`, overall `2822/2822`.
- Older `0.0.5`, `0.0.3`, `0.0.2`, and `0.0.1` references remain only in release-history entries and are intentional.

Observed:
- `SPEC_HEDIS.md` defines HEDIS domains through Domain 19 while `USER_DIRECTIVES.md` requested domains 11-20. The loop completed Domain 20 as a residual regression guard and documented the mismatch in `GLOBAL_KNOWLEDGE.md`; no public documentation update is required unless the domain specification is expanded.

## 3. Audience Alignment Notes

- Stakeholder-facing pages remain value-oriented: benchmarking and whitepaper claims emphasize compliance, speed, and deployment value rather than implementation detail.
- Developer-facing pages remain technical and copy-pastable: installation, notebooks, integration, source adapter, API reference, and WASM engine pages continue to use concrete commands and code snippets.
- The refreshed release notes balance both audiences: top-level impact is strategic, while bug-fix bullets preserve precise technical boundaries for implementers.

## 4. Draft Release Notes

### Version 0.0.6

Version `0.0.6` focuses on release hardening, browser runtime parity, and clinical correctness for HEDIS/DQM workflows.

Highlights:
- 100% conformance: ViewDefinition `134/134`, FHIRPath R4 `935/935`, CQL `1706/1706`, DQM QI-Core 2025 `47/47`, overall `2822/2822`.
- Browser-required CQL/FHIRPath runtime surfaces are available through the compiled DuckDB C++/WASM extensions.
- HEDIS clinical logic was hardened for calendar age helpers, episode aggregate folds, repeated-extension predicates, interval boundaries, stratifiers, and reference resolution.
- DQM MeasureReport output now includes parsed/evaluated group stratifier summaries.
- The Python wheel pins DuckDB to `1.5.2` so installed dependencies match the bundled native extension ABI.

Upgrade:

```bash
pip install fhir4ds-v2==0.0.6
```
