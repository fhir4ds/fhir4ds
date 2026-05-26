# CLI Contributor Notes

The `fhir4ds.cli` package owns the installed `fhir4ds` command declared in
`pyproject.toml`.

## Structure

- `main.py` defines the top-level `fhir4ds` parser and dispatches subcommands.
- `dqm.py` defines the `fhir4ds dqm` command group.
- `tests/` contains CLI-focused tests. Add tests here when changing parser
  behavior, exit codes, config translation, or user-visible output.

## Design Rules

- Keep the top-level command thin. Feature-specific parsing should live in the
  feature module, not in `main.py`.
- CLI arguments should translate into the same dataclasses used by the Python
  API. For DQM, this means `DQMRunConfig`, `MeasureSpec`, `SourceSpec`,
  `OutputSpec`, `AuditSpec`, and related config objects.
- Prefer config-file workflows for production behavior and flags for quick
  single-measure runs.
- Return stable process exit codes:
  - `0` for success.
  - `1` for a completed command with failed measure records or validation
    errors.
  - `2` for invalid command-line/config input.
- Print machine-readable details only where the command promises them. `dqm
  inspect` prints JSON; `dqm run` prints concise human status lines.
- Keep secrets out of rendered command output. Do not echo connection strings,
  credentials, or cloud secret values.

## Validation

Run focused CLI tests after changing this package:

```bash
python3 -m pytest fhir4ds/cli/tests -q
```

For DQM changes that affect batch execution or outputs, also run:

```bash
python3 -m pytest fhir4ds/dqm fhir4ds/cli/tests -q
python3 conformance/scripts/run_dqm.py
```

The repository currently has pre-existing Ruff findings outside this package, so
prefer focused lint checks for files you touched.
