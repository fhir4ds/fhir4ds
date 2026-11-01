# 📋 SPEC: QA DOMAIN CATALOG (INFRASTRUCTURE 1-10, CAMPAIGN TRACKS 11-12)

This catalog defines the 10 core infrastructure domains plus two campaign tracks for `fhir4ds-v2`. If you are assigned one of these domains, use the "Key Question" to anchor your test plan.

---

## Domain 1 — FHIRPath: Core Expression Semantics
*Package area: fhirpath_* DuckDB UDFs.*
*   **Focus**: Navigation (`Patient.name.family`), filtering (`where()`, `exists()`), type system (`ofType()`, `as()`), string/math functions, null propagation, singleton enforcement.
*   **Key Question**: Does null propagate correctly and consistently across all function categories, or does behavior differ between navigation, filtering, and math contexts?

## Domain 2 — FHIRPath: Spec-Defined Corner Cases
*Package area: Tricky semantics implementers commonly get wrong.*
*   **Focus**: `iif()` short-circuiting, `$this`/`$index` in lambdas, `repeat()` on circular references, `trace()` identity contract, union `|` vs concatenation, equality vs equivalence (`=` vs `~`).
*   **Key Question**: Where does this engine treat `=` and `~` as interchangeable when the spec says they must differ (e.g., for whitespace-padded strings or quantities)?

## Domain 3 — CQL: Translation and Semantic Correctness
*Package area: CQL translator and ELM evaluation pipeline.*
*   **Focus**: Define statements, parameter declarations, age functions, interval operators (during, overlaps, meets), list operators (`flatten`, `distinct`), aggregates, terminology (`in valueset`).
*   **Key Question**: Do interval boundary conditions (inclusive vs exclusive) behave correctly and consistently across all interval operators?

## Domain 4 — CQL: Real-World eCQM Patterns
*Package area: Interactions between features found in CMS eCQMs.*
*   **Focus**: IPP → Denominator → Numerator → Exclusions flow, Measurement Period threading, encounter vs patient contexts, value set membership, chained `with`/`such that`.
*   **Key Question**: When a patient qualifies for both an exclusion and a numerator, does population attribution behave correctly? What happens at the boundaries between populations?

## Domain 5 — SQL-on-FHIR v2: ViewDefinition Correctness
*Package area: generate_view_sql() and the correctness of its output.*
*   **Focus**: `forEach` vs `forEachOrNull`, nested `select`, `unionAll`, `where` filtering, constant injection, type column, column name collisions.
*   **Key Question**: Does `forEachOrNull` correctly preserve rows for resources where the target path is absent, or does it silently drop them like an inner join?

## Domain 6 — Data Ingestion and Schema
*Package area: FHIRDataLoader and the resources table contract.*
*   **Focus**: Bundles (transaction, batch, collection), NDJSON, line-level error propagation, malformed but valid JSON, missing `resourceType`, duplicate IDs, extremely large resources (>1MB).
*   **Key Question**: What is the failure mode when input is subtly malformed (structurally valid JSON but invalid FHIR)? Does the loader validate, silently ingest, or crash?

## Domain 7 — Performance and Scale
*Package area: Throughput, memory behavior, and scaling characteristics.*
*   **Focus**: 1k/10k/50k synthetic patients, memory leak detection (`tracemalloc`), concurrent connection pooling.
*   **Rule**: Do not flag linear slowdown as a bug. Hunt for **Scaling Cliffs** (where slowdown becomes super-linear) and memory spikes.
*   **Key Question**: Does performance degrade gracefully with scale, or is there a threshold where behavior changes qualitatively (e.g., query plan change)?

## Domain 8 — Error Handling, Robustness, and API Contract
*Package area: The gap between promise and reality.*
*   **Focus**: Actionable errors vs internal SQL errors, typed exceptions (no bare `Exception`), closed connections, invalid JSON inputs.
*   **Key Question**: Are error messages actionable—do they tell the user exactly what went wrong and where—or do they expose internal stack traces that should be abstracted?

## Domain 9 — Audit Evidence and DQM
*Package area: dqm sub-package and evidence output.*
*   **Focus**: Human-readable evidence tied to specific resource IDs, correct evidence for exclusion/exception populations, causal correctness (does it explain *why*?).
*   **Key Question**: Is the audit trail causally correct—does it accurately explain why a patient was included/excluded—or does it just report outcomes?

## Domain 10 — Installation and Environment
*Package area: Clean install, clean import, binary health.*
*   **Focus**: C++ extension load status vs Python fallback, `__version__` consistency, `pip check`, idempotency of `register(con)`.
*   **Key Question**: Is there any difference in behavior between the C++ extension path and the Python fallback, and is it possible to accidentally end up on the fallback silently?

---

## Domain 11 — API Surface Contract Testing
*Package area: Documented public entry points across the fhir4ds package.*

*   **Focus**: `connect`, `translate_cql`, `translate_library_to_population_sql`, `evaluate_measure`, viewdef parse/validate/generate/runner APIs, `parse_library`/`parse_sqlquery`/`parse_sqlview`/`SQLQueryRunner`, `fhirpath evaluate`/`fhirpath_is_valid`, terminology factory (env-var modes), notes pipeline, DQM orchestration — exercised as an external API consumer against the documented contracts (types in/out, error taxonomy, idempotency).

*   **Key Question**: Does every documented public entry point honor its documented contract, or has the documentation drifted from actual behavior (wrong types, undocumented errors, non-idempotent calls)?

## Domain 12 — medterm4ds Integration
*Package area: The fhir4ds↔medterm4ds terminology integration surface (adapters, factory, expansion, search, annotation).*

*   **Focus**: The in-process and HTTP terminology adapters behind the factory (env-var modes, `connect()` error contract, `cache_indexes`/index lifecycle); the versioned-dependency contract (bounded `medterm4ds` extras — re-verify the integration on every bump); ValueSet expansion paths (active-only vs `include_retired` policy split); code search — HTTP + in-process `$search` (`search_text`/`search_batch`: category→system mapping, `searchMode` lexical/hybrid/semantic, count semantics); annotation — `auto_coder` match grades, coding extensions, `userSelected` semantics; and the NER notes pipeline (`mode`/`min_grade`/`include_*` kwargs; medterm extraction behavior).

*   **Key Question**: Does each integration surface behave identically in-process and over HTTP against the pinned medterm4ds version — with the retired-code policy matching the use-site (membership gets retired codes for historical data; discovery stays active-only), search returning graded correctly-scoped results under the intended searchMode, and version bumps caught by the bound before they change behavior silently?
