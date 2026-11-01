# QA Handoff - SOF-VD-11 EXPLORER

Date: 2026-05-20
Phase: QA
Personality: EXPLORER

## Scope Probed

- SQL-on-FHIR ViewDefinition runner examples against current source tree.
- Parser validation, SQL generation, and DuckDB execution for simple Patient
  and Observation views.
- Patient.address unrolling via `forEach`, row preservation via
  `forEachOrNull`, `%rowIndex` filters, typed collection columns, key helper
  functions, and filtered Observation projections.
- Native C++ DuckDB extension registration compared with forced Python
  fallback registration.
- Official SQL-on-FHIR v2 spec tests and ViewDefinition integration suite.

## Specification Basis

- SQL-on-FHIR v2 ViewDefinition `select.column` defines named FHIRPath output
  columns, `where` filters rows by Boolean FHIRPath predicates, and iterator
  forms such as `forEach`/`forEachOrNull` produce row sets from repeating
  FHIRPath results.
- SQL-on-FHIR v2 key helper functions expose canonical resource/reference keys
  for View Runner use.

## Fresh Probe

Scratch probe:

```bash
python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd_11_explorer_probe.py
```

Result: PASS. It executed five synthetic ViewDefinitions through native and
forced fallback paths with identical output:

- `patient`: 2 rows
- `address`: 2 rows
- `address_or_null`: 3 rows
- `observation`: 1 row
- `array_filter`: 2 rows

The probe also verified generated SQL uses the shared `resources` table
resourceType filter and that invalid iterator/collection/where/mixed-context
inputs are rejected before execution.

## Validation Commands

```bash
python3 -m pytest fhir4ds/viewdef/tests/test_spec_compliance.py fhir4ds/viewdef/tests/integration/test_duckdb.py -q
```

Result: 492 passed.

```bash
python3 conformance/scripts/run_viewdef.py | grep -E "FAIL|ERROR|ViewDefinition|Passed|Failed|Total|PASS|OVERALL|passed|failed"
```

Result: 134/134 tests passed (100.0%).

Additional broad ViewDefinition pytest was started:

```bash
python3 -m pytest fhir4ds/viewdef -q
```

Result: pending at QA handoff; orchestrator/architect should record final
status when it returns.

## Findings

No current-source CRITICAL/HIGH/MEDIUM/LOW spec issue was found.

False alarm investigated: running a scratch script from `.ai_loop/.temp/qa`
without prepending the repo root imported an installed package and produced a
stale `getResourceKey()` Patient projection failure. The probe now inserts the
repo root into `sys.path` and the current source tree passes native/fallback
parity.

## State Update

No issues were added to `evolution.json`.
