# Documentation Audit Report

## 1. Notebook Execution Status

- `docs/notebooks/cql.ipynb`: PASS
  - Executed artifact: `/tmp/fhir4ds-docs-cql.executed.ipynb`
  - Install snippet targets `fhir4ds-v2[measures]==0.0.7` via local `dist`.
- `docs/notebooks/dqm.ipynb`: PASS
  - Executed artifact: `/tmp/fhir4ds-docs-dqm.executed.ipynb`
  - Install snippet targets `fhir4ds-v2[measures]==0.0.7` via local `dist`.
- `docs/notebooks/fhirpath.ipynb`: PASS
  - Executed artifact: `/tmp/fhir4ds-docs-fhirpath.executed.ipynb`
  - Install snippet targets `fhir4ds-v2==0.0.7` via local `dist`.
- `docs/notebooks/viewdef.ipynb`: PASS
  - Executed artifact: `/tmp/fhir4ds-docs-viewdef.executed.ipynb`
  - Install snippet targets `fhir4ds-v2==0.0.7` via local `dist`.

## 2. Stale Data Log

- `web/website/docs/user-guide/cli.md`: FIXED
  - The page described the CLI as DQM-only. Added `fhir4ds cql-server --help`,
    documented the local `$cql` facade command, and linked to the integration
    page.
- `web/website/docs/integrations/cql-tests-runner-facade.md`: FIXED
  - Added a public integration page for the new CQL tests-runner facade,
    including scope, local server command, runner harness command, and result
    serialization matrix.
  - Escaped MDX-sensitive generic type labels in the result matrix after the
    initial Docusaurus build caught the parser issue.
- `web/website/sidebars.ts`: FIXED
  - Added the CQL tests-runner facade page to the Integrations sidebar.
- `web/website/docs/getting-started/releases.md`: FIXED
  - Added the CQL tests-runner facade and `fhir4ds cql-server` harness to the
    0.0.7 highlights.
- Version references: PASS
  - Notebook install snippets, WASM docs, example docs, and homepage constants
    are aligned to target version `0.0.7`.
  - Older `0.0.x` strings in `releases.md` are historical release sections and
    were left unchanged.
- Placeholder scan: PASS
  - No `[PLACEHOLDER]`, `PLACEHOLDER`, or `TODO` entries found in audited docs
    or website source paths.
- Baseline consistency: PASS
  - Current public conformance claims match `PROC_VALIDATION.md`:
    ViewDefinition 134/134, FHIRPath 935/935, CQL 1,706/1,706, DQM 47/47,
    overall 2,822/2,822.
- Link verification: PASS WITH CANONICAL URL NOTE
  - Docusaurus build passed after the docs changes, validating internal doc
    routes and sidebar IDs.
  - Targeted public URL checks returned success for real external documentation
    and repository links.
  - Non-200 checked values were FHIR canonical URL constants in examples/API
    docs, such as `cqf-supportingEvidence`, `performanceRate`, and the b.well
    hidden-tag CodeSystem, not markdown navigation links.
- Website verification: PASS
  - `npm run build` in `web/website`: PASS.
  - `npm run test:e2e` in `web/website`: PASS, 17/17.

## 3. Audience Alignment Notes

- Stakeholder pages remain strategic and value-oriented. The homepage,
  benchmarking page, and whitepaper continue to present conformance and
  performance claims at the product level without low-level implementation
  drift.
- Developer pages are copy-pastable after the updates. The CLI page now exposes
  both DQM production commands and the local CQL facade command, while the new
  integration page documents the facade boundary clearly as a conformance
  harness rather than a general FHIR server.
- No stylistic deviations requiring remediation remain.

## 4. Draft Release Notes

Not generated because `evolution.json` does not set `config.release_date`.
The existing 0.0.7 release page was updated in place to include the CQL
tests-runner facade highlight and the verified conformance baseline remains
unchanged.
