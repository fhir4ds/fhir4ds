# 🎯 USER DIRECTIVES

<!--
This file is the PRIMARY MANDATE for the AI Initializer.
Edit this file to define your strategic goals, pipeline, and focus areas.
-->

## Strategic Goal

Implement the `medterm4ds` integration for `fhir4ds` — adding terminology
services, auto-coding, and subsumption correctness. The full plan is at
`fhir4ds-private/docs/plans/medterm4ds-integration.md`.

The integration is phased:
- **Phase 1**: Terminology abstraction layer (`fhir4ds/cql/terminology/`)
- **Phase 2**: Auto-coding loader phase (`fhir4ds/cql/loader/auto_coder.py`)
- **Phase 3**: Subsumption correctness fix (closure tables for `~`, `is`, `descendents`)
- **Phase 4**: Clinical notes NER extension (medspaCy + NER + SapBERT)

Each phase runs as a complete feature_design → feature_implementation →
code_review cycle. The orchestrator should process phases sequentially
(Phase 1 is the foundation for all subsequent phases).

## Target Version

0.0.11

## Pipeline

Each phase runs this pipeline:

1. feature_design
2. feature_implementation
3. code_review

## Feature Design Gate

The feature_design step should:
- Use the existing plan at `fhir4ds-private/docs/plans/medterm4ds-integration.md`
  as the starting point (do NOT redesign from scratch)
- Validate the plan against the current codebase (integration points may
  have shifted during the spec-compliance campaign)
- Refine into a Feature Design Document (FDD) with concrete file-level
  implementation tasks
- Architecture self-audit using ROLE_ARCHITECT.md standards
- Hand off the refined FDD to the feature_implementation step

## Feature Implementation Gate

The feature_implementation step should:
- Execute the approved FDD phase-by-phase
- Write code following existing fhir4ds patterns (see AGENTS.md)
- Add unit tests for every new module
- Add integration tests where the phase requires cross-repo interaction
  (e.g., Phase 1 needs a running medterm4ds for integration tests)
- Verify `python3 conformance/scripts/run_all.py` still passes 2822/2827
  (no regression to existing spec compliance)

## Code Review Gate

After each phase is implemented:

- Review the diff for correctness, test coverage, and architectural alignment
- Verify zero-dependency default: `fhir4ds` core must import and run without
  `medterm4ds` or `httpx` installed
- Verify the `[fhir4ds,terminology]` extra is properly gated
- Check for hardcoded model knowledge (per GLOBAL_RULES.md)
- Run full conformance suite as regression check

## Phase Definitions

### Phase 1: Terminology Abstraction (Foundation)

**Scope**: Create `fhir4ds/cql/terminology/` subpackage with:
- `TerminologyEndpoint` protocol (`expand`, `expand_intensional`, `search_text`, `search_batch`)
- `HTTPTerminologyEndpoint` (httpx-based, optional dep)
- `InProcessTerminologyEndpoint` (imports medterm4ds, optional dep)
- `get_terminology_endpoint()` factory (env-driven)
- Wire into `DependencyResolver` as fallback for unknown ValueSet URLs

**Key constraint**: Zero new hard dependencies on `fhir4ds` core. All
adapters behind `[fhir4ds,terminology]` extra. Core must continue to
work with `terminology_endpoint=None` (disabled by default).

**Exit criteria**: User can pass `terminology_endpoint=get_terminology_endpoint()`
to `execute_cql()` and have unknown ValueSet URLs resolved from medterm4ds.

### Phase 2: Auto-Coding Loader Phase

**Scope**: Create auto-coding pipeline:
- `AutoCoder` class with `augment_resource()` method
- `AutoCoderConfig` (search mode, threshold, category mapping)
- Autocoding extension builder/parser
- DuckDB cache table (`autocoding_cache`)
- Wire into `FHIRDataLoader` as optional post-load phase

**Key constraint**: Auto-coding is opt-in. Resources without
CodeableConcept.text are untouched. Original text is preserved.

**Exit criteria**: Loading `conditions_text_only.ndjson` populates
`Condition.code.coding[]` for all resources with text, every auto-coded
entry carries the autocoding extension, cache hits on duplicate text.

### Phase 3: Subsumption Correctness Fix

**Scope**: Fix three latent subsumption bugs:
- `descendents(X)` returns X unchanged (identity bug)
- `Code X ~ Code Y` uses literal tuple equality (no subsumption)
- `Code X is Code Y` falls through to IS NULL

**Approach**: Pre-expand closure tables from medterm4ds at library-load
time. Route subsumption operators through `terminology_closure` table
when available; literal-match fallback when no closure table.

**Key constraint**: Existing tests must pass unchanged without a
terminology endpoint (literal-match fallback preserved).

**Exit criteria**: CQL library using `descendents(Diabetes)` returns all
subsumed codes from loaded test data.

### Phase 4: Clinical Notes NER Extension

**Scope**: Extend auto-coding to clinical note bodies:
- medspaCy pipeline (section + ConText)
- Token-classification NER (d4data/biomedical-ner-all)
- SapBERT linking via medterm4ds
- CodeableConcept construction with provenance

**Key constraint**: Behind `[fhir4ds,ner]` extra. Phase 4 depends on
Phase 1 (terminology endpoint) and Phase 2 (auto-coding infrastructure).

## Focus Areas

- **Zero-dependency default**: `fhir4ds` core imports and runs without
  `medterm4ds`, `httpx`, `medspacy`, or `spacy` installed.
- **Optional extras**: `[fhir4ds,terminology]` for Phases 1-3;
  `[fhir4ds,ner]` for Phase 4.
- **medterm4ds public API**: `mt.connect()`, `client.search()`,
  `search_names_dataframe()` — these are the stable integration points.
- **FHIR conformance**: Do not regress 2822/2822 conformance baseline.
- **Provenance**: Every auto-coded Coding carries the autocoding extension
  with engine name, version, score, match-grade, search mode, index version.
- **Cache invalidation**: Cache key includes `index_version` so a SapBERT/BM25
  index refresh invalidates naturally.
