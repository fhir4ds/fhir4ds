# USER DIRECTIVES

This file is the primary mandate for the AI Initializer. Use it to initialize
the 0.0.9 release-preparation loop and preserve the release gate requirements
below in `evolution.json`.

## Strategic Goal

Prepare `fhir4ds-v2` for the `0.0.9` release through a full release-readiness
campaign: adversarial evolution, code review, release validation, documentation
audit, benchmark validation, and final scribe summary.

## Target Version

0.0.9

## Pipeline

1. evolution
2. code_review
3. pre_release
4. docs_audit
5. benchmarks
6. scribe

`benchmarks` is a first-class workflow. It must dispatch to
`ROLE_BENCHMARK_ENGINEER.md` and produce `benchmark_report.md`.

## Evolution Campaign

Run every infrastructure QA domain listed in
`fhir4ds-private/docs/prompts/.ai_loop/SPEC_QA_DOMAINS.md` exactly three times
each, using a different QA personality on each pass.

Minimum evolution QA passes: 30.

Requested configuration:

- `min_iterations`: 30
- `max_iterations`: 45
- `exhaustive_mode`: false
- `target_version`: `0.0.9`
- `focus_domains`: `[1,2,3,4,5,6,7,8,9,10]`
- `qa_schedule`: encode the iteration/domain/personality table below exactly

The Master Orchestrator must assign the QA domain and personality deliberately
rather than relying on a random or untracked rotation. Each domain must receive
one pass from each of these personalities:

- `SKEPTIC`
- `HISTORIAN`
- `EXPLORER`

Use this schedule unless a blocking defect requires a retry of the same domain:

| Iteration | Domain | Personality |
|---:|---:|---|
| 1 | 1 | SKEPTIC |
| 2 | 2 | SKEPTIC |
| 3 | 3 | SKEPTIC |
| 4 | 4 | SKEPTIC |
| 5 | 5 | SKEPTIC |
| 6 | 6 | SKEPTIC |
| 7 | 7 | SKEPTIC |
| 8 | 8 | SKEPTIC |
| 9 | 9 | SKEPTIC |
| 10 | 10 | SKEPTIC |
| 11 | 1 | HISTORIAN |
| 12 | 2 | HISTORIAN |
| 13 | 3 | HISTORIAN |
| 14 | 4 | HISTORIAN |
| 15 | 5 | HISTORIAN |
| 16 | 6 | HISTORIAN |
| 17 | 7 | HISTORIAN |
| 18 | 8 | HISTORIAN |
| 19 | 9 | HISTORIAN |
| 20 | 10 | HISTORIAN |
| 21 | 1 | EXPLORER |
| 22 | 2 | EXPLORER |
| 23 | 3 | EXPLORER |
| 24 | 4 | EXPLORER |
| 25 | 5 | EXPLORER |
| 26 | 6 | EXPLORER |
| 27 | 7 | EXPLORER |
| 28 | 8 | EXPLORER |
| 29 | 9 | EXPLORER |
| 30 | 10 | EXPLORER |

For each QA pass:

- Read the assigned domain from `SPEC_QA_DOMAINS.md`.
- Anchor the test plan to that domain's key question.
- Consult the relevant FHIRPath, CQL, SQL-on-FHIR, DuckDB, packaging, or DQM
  primary source before logging a spec finding.
- Test both native/C++ and Python fallback behavior where the domain touches a
  surface that can run through either path.
- Preserve all findings, remediations, validation evidence, and architectural
  lessons in the loop handoff files and applicable `AGENTS.md` files.

## Code Review Gate

After the evolution campaign exits cleanly, run `code_review`.

The review must focus on:

- correctness regressions introduced during the 0.0.9 evolution campaign,
- missing tests for changed behavior,
- release-surface risks across FHIRPath, CQL, ViewDefinition, DQM, source
  adapters, package metadata, and public docs,
- accidental broad refactors, generated-file churn, or unrelated working tree
  changes.

## Pre-Release Gate

Run the pre-release gate for target version `0.0.9`.

The Release Engineer must verify at minimum:

- package metadata and public `__version__` constants are aligned for `0.0.9`,
- conformance passes at 100% for ViewDefinition, FHIRPath, CQL, and DQM,
- the full `fhir4ds/` pytest suite passes or any failure is explicitly
  classified with evidence,
- release artifacts and install surfaces are coherent,
- generated reports or release artifacts are intentional and documented.

Required baseline commands:

```bash
python3 conformance/scripts/run_all.py
python3 -m pytest fhir4ds/ -x --tb=short
```

If package metadata, wheel contents, website install snippets, WASM release
surfaces, or public version metadata are changed, run the corresponding release
artifact checks described in repository `AGENTS.md`.

## Benchmark Gate

Benchmarks are required for this 0.0.9 release-prep campaign.

Run `benchmarks` as a standalone pipeline step after `docs_audit` and before
`scribe`.

Benchmark validation must:

- inspect the repository benchmark entry points under `benchmarks/`,
- run the most relevant non-destructive benchmark suite(s) available in this
  workspace,
- capture benchmark command lines, environment assumptions, and summarized
  results in `benchmark_report.md`,
- compare results against any existing baseline files when available,
- classify material regressions as release-blocking unless there is documented
  justification.

Do not invent a performance baseline if the repository has none. In that case,
record the fresh 0.0.9 benchmark results as the new observed baseline.

## Docs Audit Gate

Run `docs_audit` after pre-release validation and before the benchmark gate.

The audit must cover:

- public install instructions and version strings,
- release notes or changelog material for `0.0.9`,
- FHIRPath, CQL, ViewDefinition, DQM, and source-adapter user documentation
  affected by any evolution findings,
- website navigation/sidebar consistency for added or moved pages,
- stale examples that no longer match public APIs or validation behavior.

## Scribe Gate

Run `scribe` last.

The scribe output must produce a concise commit message and release-prep summary
covering:

- evolution campaign scope and domains completed,
- bugs fixed or explicitly classified,
- validation commands and results,
- benchmark outcome,
- documentation audit outcome,
- release-blocking residual risks, if any.

## Focus Areas

- Release target is `0.0.9`; do not leave package metadata or public version
  surfaces half-updated.
- Preserve 100% conformance for all implemented official suites.
- Preserve native/C++ and Python fallback parity where both paths exist.
- Do not use skips to hide supported behavior.
- Keep unrelated working tree changes isolated from release-prep changes.
- Treat benchmark regressions, packaging/version mismatches, public docs drift,
  and conformance regressions as release-blocking until resolved or explicitly
  classified.
