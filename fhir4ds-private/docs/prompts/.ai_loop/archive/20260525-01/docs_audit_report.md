# Docs Audit Report: 0.0.7

## 1. Notebook Execution Status

| Notebook | Status | Notes |
| --- | --- | --- |
| `docs/notebooks/viewdef.ipynb` | PASS | Executed with nbconvert to `/tmp/viewdef.executed.ipynb`; install snippet targets `fhir4ds-v2==0.0.7`. |
| `docs/notebooks/fhirpath.ipynb` | PASS | Executed with nbconvert to `/tmp/fhirpath.executed.ipynb`; install snippet targets `fhir4ds-v2==0.0.7`. |
| `docs/notebooks/cql.ipynb` | PASS | Executed with nbconvert to `/tmp/cql.executed.ipynb`; install snippet targets `fhir4ds-v2[measures]==0.0.7`. |
| `docs/notebooks/dqm.ipynb` | PASS | Executed with nbconvert to `/tmp/dqm.executed.ipynb`; install snippet targets `fhir4ds-v2[measures]==0.0.7`. |

## 2. Stale Data Log

Fixed:

- `web/website/docs/getting-started/releases.md`: added 0.0.7 release notes with exact conformance table and WASM rebuild note.
- `web/website/docs/getting-started/whitepaper.md`: updated standards-compliance summary to include DQM 47/47.
- `web/website/docs/examples/notebooks.md`: current notebook install snippets now target 0.0.7.
- `web/website/docs/integrations/wasm-engine.md`: translator wheel examples now target `fhir4ds_v2-0.0.7-py3-none-any.whl`.
- `web/website/src/pages/index.tsx`: landing-page product version now reports 0.0.7.
- `web/website/tests/demo.spec.ts`: landing-page assertion now expects `v0.0.7`.
- `.ai_loop/PROC_VALIDATION.md`: corrected DQM baseline from 47/44 to 47/47 and overall matrix from 2821/2821 to 2822/2822; clarified upstream DQM fixture issues are not current suite failures.

Verified:

- Historical release sections still intentionally mention older versions.
- Docusaurus production build passed after docs changes.
- Custom markdown link sweep produced Docusaurus-route false positives; the authoritative site build completed without broken-link failures.

## 3. Audience Alignment Notes

- Stakeholder pages remain value-oriented: the whitepaper and benchmarking pages emphasize speed, compliance, auditability, and deployment portability.
- Developer pages remain technical and copy-pastable: installation, notebooks, WASM integration, CLI, and source adapter docs use direct commands and current API names.
- No placeholder sections were found in the audited public docs.

## 4. Draft Release Notes

### FHIR4DS 0.0.7

FHIR4DS 0.0.7 is a release-readiness and hardening release. It preserves 100% conformance across all public standards suites while tightening packaging, loader safety, DQM audit evidence, and browser runtime assets.

Conformance baseline:

| Suite | Passed | Total | Rate |
| --- | ---: | ---: | ---: |
| ViewDefinition v2 | 134 | 134 | 100.0% |
| FHIRPath R4 | 935 | 935 | 100.0% |
| CQL | 1,706 | 1,706 | 100.0% |
| DQM QI-Core 2025 | 47 | 47 | 100.0% |
| Overall | 2,822 | 2,822 | 100.0% |

Highlights:

- Release metadata, public `__version__` exports, notebook snippets, website version text, and bundled web wheel references now consistently target 0.0.7.
- Custom FHIR resource and ValueSet table names are quoted correctly, including SQL keyword identifiers.
- File, URL, directory, and DQM ValueSet loaders reject non-object JSON at public boundaries with typed errors.
- DQM audit narratives use effective exclusion/exception population masks so evidence text matches final attribution.
- Optimized CQL interval overlap SQL now handles null low bounds according to CQL interval semantics.
- Native DuckDB extensions and browser WASM side modules were rebuilt and release artifacts were verified through clean install, full conformance, full package pytest, and browser Playwright gates.

Documentation audit complete; ready for scribe workflow.
