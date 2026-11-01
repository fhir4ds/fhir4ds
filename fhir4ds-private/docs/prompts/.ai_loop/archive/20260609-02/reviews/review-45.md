# Code Review Findings: Spec Compliance Milestone

Date: 2026-05-20
Workflow: code_review
Exit reason: CLEAN after remediation

## Scope

Reviewed current source, AGENTS.md, GLOBAL_RULES.md, relevant GLOBAL_KNOWLEDGE.md entries, active evolution.json, ViewDefinition parser/generator/type validation code, source-adapter SQL construction, and selected DuckDB parity boundaries. Archived prior workflow outputs were not used as proof of behavior.

## Findings

### REV-001 - CRITICAL - CSVSource path SQL injection

`fhir4ds/sources/csv.py:83` builds `read_csv_auto('{self._path}')` with the raw user path, then `register()` executes the resulting projection at `fhir4ds/sources/csv.py:86`. This bypasses the shared `quote_sql_literal()` helper used by other source adapters.

Fresh contained repro: a malicious path ending in `'); DROP TABLE sentinel; --` caused a DuckDB in-memory `sentinel` table to be dropped during `CSVSource.register()`.

Recommended fix: use `quote_sql_literal(self._path)` when building the scan expression, and add a regression test matching the existing FileSystemSource path-escaping coverage.

### REV-002 - HIGH - ViewDefinition.from_dict() drifts from parser validation and can drop filters

`fhir4ds/viewdef/types.py:576-580` accepts `resource`, `profile`, and `fhirVersion` directly in `ViewDefinition.from_dict()` without the parser's ResourceType, array-shape, or FHIRVersion binding checks. `fhir4ds/viewdef/types.py:666` stores `where` directly; `fhir4ds/viewdef/generator.py:974-981` then ignores parser-supported dict/string root `where` inputs when they come from `from_dict()`.

Fresh repro: `ViewDefinition.from_dict()` accepted `resource=['Patient']`, `profile='http://x'`, and `fhirVersion=['bogus']`. It also generated SQL without an `active = true` root filter when `where={'path': 'active = true'}` was supplied.

Recommended fix: make `from_dict()` reuse the parser's root metadata and where parsing helpers, or delegate dict construction through `parse_view_definition()`.

### REV-003 - HIGH - Public ViewDefinition join SQL generation leaves identifiers unvalidated

`fhir4ds/viewdef/join.py:130-145` interpolates `join.resource` and `join.name` directly into generated JOIN SQL, while `fhir4ds/viewdef/parser.py:247-268` accepts join aliases/resources without SQL-name or ResourceType validation. The main `SQLGenerator` currently does not integrate joins, but `generate_join()` and `JoinGenerator` are public surfaces.

Recommended fix: validate `join.name` with `validate_sql_name()`, validate `join.resource` against `KNOWN_FHIR_RESOURCE_TYPES`, and quote generated join table aliases/table references consistently.

## Validation

- `python3 -m pytest fhir4ds/sources/tests/unit/test_csv.py fhir4ds/sources/tests/unit/test_filesystem.py fhir4ds/sources/tests/unit/test_relational.py -q` - 71 passed
- `python3 -m pytest fhir4ds/viewdef/tests/unit fhir4ds/viewdef/tests/test_spec_compliance.py -q` - 759 passed
- `python3 -m pytest fhir4ds/viewdef/tests/integration/test_duckdb.py -q` - 29 passed
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_number_fastpath_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_extension_parity.py fhir4ds/cql/duckdb/tests/integration/test_core_forced_backend_parity.py -q` - 3 passed
- Manual repro scripts confirmed REV-001 and REV-002.

## Remediation

All three findings were fixed and verified before archiving review-45.

- `REV-001`: `CSVSource.register()` now builds the DuckDB CSV scan with `quote_sql_literal(self._path)`. Added a regression test using a malicious filename that previously could drop a sentinel table.
- `REV-002`: `ViewDefinition.from_dict()` now delegates through `parse_view_definition()`, so root `resource`, `profile`, `fhirVersion`, joins, select fields, and `where` normalization share the parser validation boundary.
- `REV-003`: `Join` construction and join parsing now validate `Join.name` as SQL-on-FHIR `sql-name` and `Join.resource` against the FHIR ResourceType binding. Public join SQL generation quotes generated table names and aliases.

## Remediation Validation

- `python3 -m pytest fhir4ds/sources/tests/unit/test_csv.py fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_join.py fhir4ds/viewdef/tests/unit/test_security.py -q` - 184 passed
- `python3 -m pytest fhir4ds/sources/tests/unit/test_csv.py fhir4ds/sources/tests/unit/test_filesystem.py fhir4ds/sources/tests/unit/test_relational.py fhir4ds/viewdef -q` - 865 passed
- `python3 conformance/scripts/run_all.py` - overall 2822/2822, 100%
- `python3 -m pytest fhir4ds/ -x --tb=short` - 7331 passed, 5 skipped, 9 warnings
