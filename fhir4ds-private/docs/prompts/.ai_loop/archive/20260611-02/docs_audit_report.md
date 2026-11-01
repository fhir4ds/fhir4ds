# Docs Audit Report - Release 0.0.9

## 1. Notebook Execution Status

- `docs/notebooks/fhirpath.ipynb`: PASS. Executed with nbconvert to
  `.temp/docs_notebooks/fhirpath.executed.ipynb`; no error outputs.
- `docs/notebooks/cql.ipynb`: PASS. Executed with nbconvert to
  `.temp/docs_notebooks/cql.executed.ipynb`; no error outputs.
- `docs/notebooks/viewdef.ipynb`: PASS. Executed with nbconvert to
  `.temp/docs_notebooks/viewdef.executed.ipynb`; no error outputs.
- `docs/notebooks/dqm.ipynb`: PASS. Executed with nbconvert to
  `.temp/docs_notebooks/dqm.executed.ipynb`; no error outputs.

All notebook install snippets point at `fhir4ds-v2==0.0.9` with local
`../../dist` wheel lookup.

## 2. Stale Data Log

- Fixed `README.md` compliance table. It still reported FHIRPath as
  `934/935 (99.9%)` and older CQL/ViewDefinition counts. The table now matches
  the live baseline: FHIRPath `935/935`, CQL `1706/1706`, ViewDefinition
  `134/134`, and DQM `47/47`.
- Current public install/version references in notebooks, website notebook
  docs, WASM engine docs, homepage version badge, and website tests are aligned
  to `0.0.9`.
- Remaining `0.0.8` references are historical entries in
  `web/website/docs/getting-started/releases.md`, not current install
  instructions.
- Placeholder scan found no `[PLACEHOLDER]`, `TODO`, or `TBD` markers in the
  audited public docs.
- Lightweight relative-link existence check found no missing internal relative
  links in `README.md`, `docs/`, or `web/website/docs/`.

## 3. Audience Alignment Notes

- Stakeholder pages retain strategic conformance and value framing. The current
  whitepaper and benchmarking pages use the same conformance baseline as the
  release gate.
- Developer pages remain technical and copy-pastable. The CQL facade CLI docs
  and sidebar entry are present; those changes appear to be pre-existing
  workspace work and were not altered by this audit.
- WASM integration docs now reference the 0.0.9 translator wheel and preserve
  the `deps=False` Pyodide install guidance required for browser installs.

## 4. Draft Release Notes

`web/website/docs/getting-started/releases.md` now includes a 0.0.9 section:

- Release-readiness campaign across FHIRPath, CQL, SQL-on-FHIR
  ViewDefinition, ingestion/source adapters, DQM audit evidence, installation,
  and environment behavior.
- Version and artifact alignment across package metadata, public subpackage
  versions, notebooks, website references, and WASM translator wheel assets.
- Validation gates covering conformance, package pytest, documentation audit,
  benchmark validation, and final scribe handoff.

Current conformance baseline for release notes and public docs:

| Suite | Passed | Total | Rate |
| --- | ---: | ---: | ---: |
| ViewDefinition v2 | 134 | 134 | 100.0% |
| FHIRPath R4 | 935 | 935 | 100.0% |
| CQL | 1,706 | 1,706 | 100.0% |
| DQM QI-Core 2025 | 47 | 47 | 100.0% |
| Overall | 2,822 | 2,822 | 100.0% |
