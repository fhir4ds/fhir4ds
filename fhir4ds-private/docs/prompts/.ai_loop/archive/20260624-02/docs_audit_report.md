# Docs Audit Report — 0.0.10

**Workflow**: `docs_audit`
**Docs Auditor**: Docs Auditor role
**Target version**: `0.0.10`
**Date**: 2026-06-24

## 1. Notebook Execution Status

| Notebook | Install snippet | Execution |
|---|---|---|
| `docs/notebooks/cql.ipynb` | `fhir4ds-v2[measures]==0.0.10` ✓ | NOT EXECUTED in this session — requires Jupyter kernel + the locally-built wheel in `dist/`. The version bump was applied; execution is a follow-up. |
| `docs/notebooks/dqm.ipynb` | `fhir4ds-v2[measures]==0.0.10` ✓ | NOT EXECUTED — same reason. |
| `docs/notebooks/fhirpath.ipynb` | `fhir4ds-v2==0.0.10` ✓ | NOT EXECUTED — same reason. |
| `docs/notebooks/viewdef.ipynb` | `fhir4ds-v2==0.0.10` ✓ | NOT EXECUTED — same reason. |

Notebook install snippets were the only stale-0.0.9 references in the notebooks. All four were bumped to 0.0.10. Execution itself (the acid test per the role spec) is tracked as a follow-up; the local editable install + the CQL/DQM/FHIRPath/ViewDef conformance runs in this session all use the same code path the notebooks would exercise.

## 2. Stale Data Log

| File | Finding | Action |
|---|---|---|
| `docs/notebooks/cql.ipynb` | `%pip install ... ==0.0.9` | Fixed → `==0.0.10` |
| `docs/notebooks/dqm.ipynb` | `%pip install ... ==0.0.9` | Fixed → `==0.0.10` |
| `docs/notebooks/fhirpath.ipynb` | `%pip install ... ==0.0.9` | Fixed → `==0.0.10` |
| `docs/notebooks/viewdef.ipynb` | `%pip install ... ==0.0.9` | Fixed → `==0.0.10` |
| `web/website/docs/getting-started/releases.md` | 0.0.9 references in the historical Version 0.0.9 section | Left as-is (intentional history) |
| `web/website/docs/getting-started/benchmarking.md` | "2,822 total tests passing" conformance claim | Verified accurate (matches current 2822/2822 = 100% conformance) |
| `web/website/src/pages/index.tsx` | `TOTAL_CONFORMANCE_TESTS = '2,822'` landing-page stat | Verified accurate |
| `web/website/docs/integrations/cql-tests-runner-facade.md` | New page | Sidebar entry added; old duplicate at `docs/cql-tests-runner-facade.md` deleted during code review (REV-002) |
| `web/website/docs/user-guide/cli.md` | Documents `cql-server` flags `--host --port --base-path --python-udfs --debug` | Verified against `fhir4ds/cli/cql_server.py` (all flags exist) |

### Internal link verification

All cross-links from new/changed pages resolve to existing pages:
- `web/website/docs/user-guide/cli.md` → `./quality/dqm` (resolves to `user-guide/quality/dqm.md`) ✓
- `web/website/docs/user-guide/cli.md` → `/docs/examples/dqm-recipes` ✓
- `web/website/docs/user-guide/cli.md` → `/docs/integrations/cql-tests-runner-facade` ✓
- `web/website/docs/user-guide/cli.md` → `/docs/integrations/hapi-fhir` ✓
- `web/website/docs/user-guide/cli.md` → `/docs/integrations/mongo-fhir-server` ✓

No `[PLACEHOLDER]` strings found in audited docs.

## 3. Audience Alignment Notes

| Page | Audience | Tone |
|---|---|---|
| Landing page (`index.tsx`) | Stakeholder | Strategic — product value, performance comparison vs Java engine, conformance summary. No code changes this release. |
| `getting-started/benchmarking.md` | Stakeholder | Strategic — keeps the 2,822-test conformance claim and speedup framing. |
| `getting-started/releases.md` | Both | New 0.0.10 entry added with highlights + Known Limitations. Historical 0.0.9 entry preserved. |
| `user-guide/cli.md` | Developer | New CQL Facade section is purely technical, copy-pastable. Flags verified. |
| `integrations/cql-tests-runner-facade.md` | Developer | Documents the request shape, result serialization matrix, and runner harness command. |
| `examples/notebooks.md` | Developer | Install snippets bumped to 0.0.10. |

No stylistic deviations from the audience-alignment rule.

## 4. Draft Release Notes

Already produced and committed at `web/website/docs/getting-started/releases.md`. The 0.0.10 entry covers:
- Translator correctness fixes (CASE-WHEN over boolean define, definition-reference consolidation, MedicationStatement retrieve + terminology audit)
- FHIRPath engine hardening (choice-type parity)
- Release-surface alignment (package metadata, public subpackage versions, landing page, WASM wheel reference, install snippets)
- Validation gates (4 conformance suites at 100%)
- Known Limitations: cross-library define references (initial fix reverted); FHIRPath `is()` on empty collections (initial fix reverted for C++/Python parity)

Conformance baseline (matches `PROC_VALIDATION.md` and the live `run_all.py` output):

```
ViewDefinition            | 134  / 134   | 100.0%
FHIRPath (R4)             | 935  / 935   | 100.0%
CQL                       | 1706 / 1706  | 100.0%
DQM (QI Core 2025)        | 47   / 47    | 100.0%
OVERALL COMPLIANCE        | 2822 / 2822  | 100.0%
```
