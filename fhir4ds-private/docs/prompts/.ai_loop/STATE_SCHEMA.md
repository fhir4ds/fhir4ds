# STATE SCHEMA

Canonical state contract for the `.ai_loop` prompts. Role prompts may summarize this file, but this file wins when there is ambiguity.

---

## 1. `evolution.json`

Required fields:

```json
{
  "phase": "QA",
  "iteration": 1,
  "audit_status": "PENDING",
  "exit_reason": null,
  "workflow": "evolution",
  "pipeline": ["evolution"],
  "pipeline_step": 0,
  "qa_personality": null,
  "config": {},
  "issues": []
}
```

### Workflows

Valid `workflow` values:
- `feature_design`
- `feature_implementation`
- `bug_fix`
- `evolution`
- `code_review`
- `pre_release`
- `docs_audit`
- `benchmarks`
- `scribe`
- `retrospective`
- `dependency_upgrade`
- `WAIT_FOR_USER_APPROVAL`
- `null`

`null` means the current workflow is complete and the Master Orchestrator may advance `pipeline_step`.

### Phases

Valid phases by workflow:
- `feature_design`: `DESIGN`, `DESIGN_AUDIT`, `REFINEMENT`, `APPROVAL`
- `feature_implementation`: `IMPLEMENTATION`, `VERIFY`
- `bug_fix`: `FIX`
- `evolution`: `QA`, `FIX`, `ARCHITECT`
- `code_review`: `REVIEW`
- `pre_release`: `RELEASE`
- `docs_audit`: `DOCS_AUDIT`
- `benchmarks`: `BENCHMARKS`
- `scribe`: `SCRIBE`
- `retrospective`: `RETROSPECTIVE`
- `dependency_upgrade`: `RECON`, `IMPACT`, `BASELINE`, `UPGRADE`, `REPORT`
- `WAIT_FOR_USER_APPROVAL`: `WAIT_FOR_USER_APPROVAL`

### Exit Reasons

Valid `exit_reason` values:
- `CLEAN`
- `MAX_ITERATIONS`
- `BLOCKED_ENVIRONMENT`
- `NEEDS_USER_APPROVAL`
- `DEGRADED`
- `null`

Set `exit_reason` whenever a workflow finishes or cannot proceed.

### Config Fields

Common config fields:
- `min_iterations`: minimum evolution iterations before clean exit is eligible.
- `max_iterations`: maximum evolution iterations before degraded exit.
- `exhaustive_mode`: if true, continue evolution until `max_iterations` even if clean-exit criteria are met.
- `target_version`: release version.
- `wheel_filename`: exact wheel filename when relevant.
- `feature_plan_path`: approved feature plan path.
- `personality_override`: forced QA personality.
- `specialist_domain_override`: forced QA domain.
- `focus_domains`: QA domain allowlist.
- `qa_schedule`: optional ordered QA schedule entries with `iteration`, `domain`, and `personality`.
- `benchmark_commands`: optional ordered benchmark commands to run during the `benchmarks` workflow.
- `benchmark_baseline_path`: optional benchmark baseline or previous report path for comparison.
- `target_duckdb_version`: exact upstream DuckDB version under evaluation for the `dependency_upgrade` workflow (e.g. `"1.5.5"`, `"2.0.0"`).
- `duckdb_upgrade_mode`: one of `monitor` (recon only, default), `investigate` (read-only report), `upgrade` (execute the full bump); governs `ROLE_DEPENDENCY_UPGRADER.md`.
- `bug_fix_target`: concise description of a specific human-requested bug.
- `bug_fix_validation`: focused validation command(s) or expected proof for a specific bug fix.
- `notes`: human and orchestrator guidance.

---

## 2. Issue Objects

Each issue in `issues` should use this shape:

```json
{
  "id": "QA-001",
  "severity": "HIGH",
  "status": "OPEN",
  "category": "SPEC_VIOLATION",
  "spec_citation": "FHIRPath §5.1",
  "evidence": "Actual vs expected and reproducer",
  "root_cause": null,
  "resolution": null,
  "verified_in": null
}
```

### Severities

Valid severities:
- `CRITICAL`
- `HIGH`
- `MEDIUM`
- `LOW`

### Statuses

Active statuses:
- `NEW`
- `OPEN`
- `CONFIRMED`
- `IN_PROGRESS`
- `RETRY_QA`

Terminal statuses:
- `RESOLVED`
- `VERIFIED`
- `DEFERRED`
- `UNCONFIRMED`
- `INTENDED`
- `NEEDS_CONTEXT`

Open issue count means any issue whose status is not terminal.

### Terminal Dismissals

These terminal statuses do not count as open bugs:
- `INTENDED`
- `UNCONFIRMED`
- `DEFERRED`

`NEEDS_CONTEXT` is terminal for the current autonomous run but must be surfaced to the human.

---

## 3. Control Flags

Top-level control flags:
- `RETRY_QA`: boolean. If true after Architect phase, return to QA without incrementing `iteration`.
- `retry_note`: string. Specific edge cases or failures that QA must address on retry.

Prefer lowercase new fields (`retry_note`) for new state. Preserve legacy uppercase flags when already present.

---

## 4. Completion Contract

Workflow completion is file-state based:
- `workflow` is `null`.
- `exit_reason` is non-null.
- Required handoff/report files for that workflow exist.
  - `bug_fix` requires `engineer_handoff.md`.
  - `code_review` requires `code_review_findings.md`.
  - `pre_release` requires `release_readiness_report.md`.
  - `docs_audit` requires `docs_audit_report.md`.
  - `benchmarks` requires `benchmark_report.md`.
  - `dependency_upgrade` requires `duckdb_upgrade_report.md`.
  - `scribe` requires `.temp/draft_commit.txt`.

Do not rely on exact printed chat sentinels for orchestration. Chat output may summarize completion, but state files are authoritative.
