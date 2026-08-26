# CQL-to-SQL Translator: Architectural Guide

**Start here.** This document covers principles, component responsibilities, antipatterns, and
rules for working in the translator. Read this before touching any translator code.

For deeper detail:
- `DESIGN.md` — three-phase pipeline, shape metadata, CTE organization, ExprUsage rules
- `TECHNICAL_SPECIFICATION.md` — translation patterns, SQL conventions, supported/unsupported features

---

## What the Translator Is

A **population-first CQL-to-SQL compiler** targeting DuckDB with FHIR UDFs. It takes a parsed
CQL library AST and produces a SQL query that evaluates the measure across an entire patient
population in a single pass. Output is one row per patient.

It is NOT a general CQL interpreter. It handles the subset of CQL used in FHIR-based quality
measures (QI Core / US Core profiles, HEDIS-style population logic). Edge cases in general CQL
that don't appear in real measures are out of scope.

---

## Guiding Principles

### 1. CQL is the source of truth for all logic

If logic is defined in CQL — status filters, value subsets, filter conditions — the translator
must read it from the CQL AST. It must not duplicate that logic in JSON config files, Python
dicts, or hardcoded strings. A config file that duplicates CQL logic will silently drift out
of sync when the CQL changes.

**Corollary:** if the translator cannot read something from the CQL AST, that is a translator
bug to fix — not a reason to add a fallback config file.

### 2. Pure AST pipeline

Translation operates on structured AST objects (`SQLExpression` and its subtypes) from input
to output. String manipulation of SQL is forbidden mid-pipeline. The only place SQL strings
are produced is in the final `to_sql()` serialization step.

**Why:** string-based SQL cannot be analyzed, rewritten, or validated. AST nodes can. The
retrieve optimizer, placeholder resolver, and CTE deduplication all depend on being able to
inspect and rewrite the AST after initial translation.

### 3. Context is the single source of truth at runtime

`SQLTranslationContext` is the one place all version-sensitive data lives during translation.
No translator module loads its own resources. Everything is loaded once at startup by
`CQLToSQLTranslator.__init__` and threaded into context.

The five context fields that carry versioned data:
- `context.fhir_schema` — FHIR R4 StructureDefinitions (type queries, UDF inference)
- `context.profile_registry` — QI Core profile mappings, extension URLs, component patterns
- `context.column_mappings` — FHIRPath → precomputed column name mappings
- `context.choice_type_prefixes` — column name prefixes for choice type elements
- `context.extension_paths` — QI Core virtual property → US Core extension URL mappings

### 4. Three-layer schema separation

Schema knowledge is divided by responsibility:

```
FHIRSchemaRegistry     — FHIR base schema only (StructureDefinitions, type→UDF mapping)
                          reads from: ModelConfig.fhir_r4_dir

ProfileRegistry        — Profile/model knowledge (extension URLs, component patterns,
                          profile name→resource type mappings, negation profiles)
                          reads from: ModelConfig.us_core_dir + ModelConfig.qicore_dir

SQLTranslationContext  — Runtime single source of truth
                          populated by: CQLToSQLTranslator.__init__
```

`FHIRSchemaRegistry` does not know about profiles. `ProfileRegistry` does not know about
StructureDefinitions. Neither loads anything at call time — both are loaded once at startup.

### 5. Fail fast, never silently compensate

If a required component is missing (no `fhir_schema` on context, no schema file on disk for
a known resource type), raise a clear error. Silent fallbacks that produce plausible-but-wrong
SQL are far more dangerous than hard failures. A test failure is easy to fix; a quietly wrong
measure result may go undetected.

### 6. Terminology is stable; schema is versioned

`resources/terminology/` files (LOINC codes, code system URLs, valueset prefixes, status codes)
are stable across FHIR versions and may be loaded as module-level constants. Files in
`resources/schema/` are version-sensitive and must be loaded through `ModelConfig`-aware
registries, never with hardcoded paths.

---

## Component Map

### `translator.py` — `CQLToSQLTranslator`
**Owns:** orchestration of the three translation phases; translator public API; startup wiring
of all registries and context fields.
**Does not own:** expression translation logic, CTE building, profile resolution.
**Rule:** the only place `FHIRSchemaRegistry` and `ProfileRegistry` are instantiated.

### `context.py` — `SQLTranslationContext`
**Owns:** symbol tables, scope stack, CTE registry, all versioned runtime data.
**Does not own:** translation logic of any kind.
**Rule:** a passive data container. No business logic belongs here.

### `expressions.py` — `ExpressionTranslator`
**Owns:** translation of CQL expression AST nodes to `SQLExpression` AST nodes.
**Does not own:** CTE construction, resource loading, profile resolution (uses
`self.context.profile_registry`).

### `cte_builder.py`
**Owns:** construction of retrieve CTEs with precomputed columns.
**Does not own:** expression translation, profile registry loading.
**Rule:** `context.fhir_schema` must be set before any CTE is built. If it is None, raise
`RuntimeError` — this indicates a translator initialization bug.

### `fhir_schema.py` — `FHIRSchemaRegistry`
**Owns:** FHIR R4 StructureDefinition loading; answers to "what type is this element?",
"what UDF should I use?", "what are the choice types for value[x]?"; `column_mappings` and
`choice_type_prefixes` lazy properties.
**Does not own:** profile mappings, extension URLs, component patterns, precomputed column
decisions.
**Rule:** always instantiated with `model_config=` argument. Never `FHIRSchemaRegistry()`.

### `profile_registry.py` — `ProfileRegistry`
**Owns:** QI Core profile name → FHIR resource type mappings; profile URL → resource type;
negation profile detection; extension URL mappings; component profile keywords.
**Does not own:** StructureDefinition knowledge, column mappings.
**Rule:** always instantiated via `ProfileRegistry.from_model_config(config)` in production
code. `get_default_profile_registry()` exists as a fallback for call sites that don't yet
have context access — prefer `context.profile_registry` wherever context is available.

### `model_config.py` — `ModelConfig`
**Owns:** version strings and derived versioned directory paths for FHIR R4, US Core, QI Core.
**Does not own:** loading logic, registry instantiation.
**Rule:** `DEFAULT_MODEL_CONFIG` targets FHIR R4 4.0.1 / US Core 3.1.1 / QI Core 4.1.1.

### `column_generation.py`
**Owns:** mapping FHIRPath property paths to precomputed column metadata (names, UDFs, SQL types).
**Does not own:** its own resource loading — receives `fhir_schema`, `column_mappings`, and
`choice_type_prefixes` as parameters from callers.
**Rule:** `build_column_definitions()` requires `fhir_schema` — raises `ValueError` if None.

### `patterns/retrieve.py` — `RetrieveTranslator`
**Owns:** translation of CQL `Retrieve` expressions; profile normalization; negation filtering.
**Does not own:** profile registry loading — uses `self.context.profile_registry`.

### `property_scanner.py`
**Owns:** walking a SQL AST to find all `fhirpath_*` call sites (for retrieve optimizer).
**Does not own:** anything stateful.

### `component_codes.py`
**Owns:** LOINC code → column name mappings for BP-like composite observations.
**Does not own:** nothing else. This is stable terminology; not version-sensitive.
**Rule:** may remain a module-level loaded constant. Lives in `resources/terminology/`.

### `status_filter_extractor.py`
**Owns:** dynamic extraction of status filter logic from CQL library ASTs.
**Does not own:** fallback status logic. Status filters are always defined in CQL; if
extraction fails, that is a bug to fix in the extractor, not a reason to add config fallbacks.

---

## Do's and Don'ts

### DO: Use context for all versioned data

```python
# Correct
registry = self.context.profile_registry or get_default_profile_registry()
mappings = context.column_mappings

# Wrong — bypasses versioning, ignores custom ModelConfig
registry = get_default_profile_registry()
mappings = _load_column_mappings()
```

### DO: Instantiate registries with model_config

```python
# Correct
schema = FHIRSchemaRegistry(model_config=self._model_config)

# Wrong — uses legacy hardcoded path, ignores versioning
schema = FHIRSchemaRegistry()
```

### DO: Raise on missing required context, not create fallbacks

```python
# Correct
if fhir_schema is None:
    raise RuntimeError(
        "fhir_schema is required. This is a translator initialization bug."
    )

# Wrong — silently creates a misconfigured registry
if fhir_schema is None:
    fhir_schema = FHIRSchemaRegistry()
    fhir_schema.load_default_resources()
```

### DO: Read logic from the CQL AST

```python
# Correct — extractor reads the actual CQL definition
status_filter = status_filter_extractor.extract(cql_ast, function_name)

# Wrong — duplicates CQL logic in a config file that will silently drift
status_filter = _STATUS_FILTER_FALLBACKS.get(function_name)
```

### DO: Preserve Clinical Type Shape Through Aliases

CQL clinical values are not FHIR resources. Code and Concept equivalence must
use CQL clinical semantics, and ValueSet/CodeSystem remain Vocabulary values
until a terminology membership boundary unwraps them to a URL. Static clinical
type metadata must propagate through definitions, query `let`/`return`, and
`singleton from` expressions; otherwise `is`/`as` falls through to FHIR
`resourceType` checks against JSON-shaped CQL values.

### DO: Keep the AST pipeline pure

```python
# Correct — build AST nodes
condition = SQLBinaryOp(
    operator="=",
    left=SQLFunctionCall(name="fhirpath_text", args=[resource, SQLLiteral("status")]),
    right=SQLLiteral("active"),
)

# Wrong — string manipulation mid-pipeline
condition = SQLRaw(f"fhirpath_text(r.resource, 'status') = 'active'")
```

### DON'T: Load resources at module level for version-sensitive data

```python
# Wrong — loads at import time, ignores ModelConfig
_COLUMN_MAPPING = json.load(open("resources/fhir/r4/column_mappings.json"))

# Correct — loaded once at startup via FHIRSchemaRegistry, accessed via context
mappings = context.column_mappings
```

### DON'T: Hardcode profile or extension knowledge in Python code

```python
# Wrong — profile knowledge belongs in qicore-profiles.json
if resource_type == "USCoreBloodPressureProfile":
    resource_type = "Observation"

# Correct — ProfileRegistry resolves this from versioned config
resolved = registry.resolve_named_profile(resource_type)
if resolved:
    resource_type, profile_url = resolved
```

### DON'T: Add new Strategy 2 string templates

Strategy 2 (string template fluent functions) is a transitional pattern. Existing entries
remain for backward compatibility. No new entries. New fluent functions must be implemented
as proper AST-based translations.

---

## Antipatterns Found in This Codebase (and Fixed)

These patterns were found and removed. Do not reintroduce them.

### 1. Module-level resource loading for version-sensitive data

`column_generation.py` previously had:
```python
_COLUMN_MAPPING: Optional[Dict[str, str]] = None

def _load_column_mappings() -> Dict[str, str]:
    global _COLUMN_MAPPING
    if _COLUMN_MAPPING is None:
        path = Path(__file__).parent... / "resources" / "fhir" / "r4" / "column_mappings.json"
        ...
    return _COLUMN_MAPPING
```

**Why it's wrong:** loaded at import time from a hardcoded legacy path, ignoring `ModelConfig`.
Changing versions had no effect. Fixed by moving to `FHIRSchemaRegistry.column_mappings` and
threading through context.

### 2. Bare FHIRSchemaRegistry() instantiation as a fallback

`cte_builder.py` previously had:
```python
if fhir_schema is None:
    fhir_schema = FHIRSchemaRegistry(model_config=DEFAULT_MODEL_CONFIG)
    fhir_schema.load_default_resources()
```

**Why it's wrong:** `context.fhir_schema` being `None` at CTE build time is a translator
initialization bug. Silently creating a new registry hides the bug, creates a fresh registry
on every translation (performance), and bypasses any custom `ModelConfig`. Fixed by raising
`RuntimeError`.

### 3. CQL logic duplicated in a JSON fallback file

`fluent_functions.py` uses `_STATUS_FILTER_FALLBACKS` loaded from `status_filters.json` as a
fallback when `status_filter_extractor.py` fails to read the CQL AST. The fallback contains
hand-translated versions of `Status.cql` function bodies.

**Why it's wrong:** two sources of truth for the same logic. When `Status.cql` changes (new
QI Core version), the JSON must be manually updated. Failure to update produces silently wrong
SQL with no error. The correct fix is improving `status_filter_extractor.py` to reliably read
the CQL, then removing the fallback.

**Current status:** still present. Tracked for removal once the extractor is comprehensive.

### 4. get_default_profile_registry() called instead of context.profile_registry

Multiple files previously called `get_default_profile_registry()` directly, bypassing whatever
`ProfileRegistry` instance the translator was configured with. This meant a custom `ModelConfig`
had no effect on profile resolution in those code paths.

Fixed: all call sites now use `self.context.profile_registry or get_default_profile_registry()`
so the context-provided registry wins when available.

### 5. Module-level globals in expressions.py for extension paths

`expressions.py` previously had:
```python
_EXTENSION_PATHS = _load_extension_paths()  # loaded at import, legacy path

# then at use site:
ext_paths = self.context.extension_paths if self.context.extension_paths is not None \
            else _EXTENSION_PATHS
```

**Why it's wrong:** the fallback silently masked failures to set `context.extension_paths`.
If the context field was not populated, incorrect (legacy) extension paths were used without
any warning. Fixed by removing the global and using `self.context.extension_paths or {}`.

---

## How to Add Common Things

### New CQL fluent function
1. Implement translation in `expressions.py` as an AST-based translation (not Strategy 2)
2. Add tests in `tests/unit/test_v2_expressions.py`
3. If it involves status filtering, implement extraction in `status_filter_extractor.py`
4. Do not add to `status_filters.json`

### New FHIR resource type
1. Add StructureDefinition JSON to `resources/schema/fhir-r4-4.0.1/`
2. Add to `load_default_resources()` list in `fhir_schema.py`
3. Add any precomputed column mappings to `resources/schema/fhir-r4-4.0.1/column_mappings.json`
4. No Python code changes needed for basic retrieves

### New QI Core profile
1. Add to `resources/schema/qicore-4.1.1/qicore-profiles.json` under the appropriate section
2. If it adds component columns (like blood pressure), add LOINC codes to
   `resources/terminology/component_codes.json` and keywords to `component_profile_keywords`
3. No Python code changes needed

### New FHIR version (e.g., R4B or R5)
1. Create `resources/schema/fhir-r4b-4.3.0/` with StructureDefinitions and config files
2. Copy and update `column_mappings.json`, `choice_type_prefixes.json`, `fhir_type_mappings.json`
3. Update `ModelConfig` with the new version option
4. `FHIRSchemaRegistry` and `ProfileRegistry` pick up new paths automatically

### New US Core or QI Core version
1. Create the versioned dir (`resources/schema/us-core-6.1.0/` etc.)
2. Populate `extension_paths.json` (US Core) or `qicore-profiles.json` (QI Core)
3. Update `ModelConfig` version strings
4. No translator Python code changes needed

---

## Resources Directory Layout

```
resources/
  schema/                        # Version-sensitive — always use ModelConfig paths
    fhir-r4-4.0.1/
      *.json                     # FHIR R4 StructureDefinitions
      column_mappings.json       # FHIRPath → precomputed column names
      choice_type_prefixes.json  # Column prefix → choice type indicator
      fhir_type_mappings.json    # FHIR type → UDF name + SQL type
    us-core-3.1.1/
      extension_paths.json       # QI Core virtual property → extension URL
    qicore-4.1.1/
      qicore-profiles.json       # Profile name/URL → FHIR base type + negation info
      model_properties.json      # QI Core virtual property definitions
  fhir/r4/                       # Legacy — fallback only, do not add new files here
  profiles/                      # Legacy — fallback only, do not add new files here
  terminology/                   # Stable — not version-sensitive, module-level load is OK
    component_codes.json         # BP LOINC codes → column names + FHIRPath
    status_filters.json          # Status filter fallbacks (to be removed — see antipattern 3)
    codesystem_prefixes.json     # Code system name → URL
    valueset_prefixes.json       # Valueset URL prefix config
    terminology_property_defaults.json
```

---

## Key Data Structures

- `ModelConfig` — version strings + derived paths; passed to translator constructor
- `FHIRSchemaRegistry` — answers FHIR type/element/UDF questions; has `column_mappings`,
  `choice_type_prefixes` lazy properties
- `ProfileRegistry` — answers profile/model questions; has `extension_paths`,
  `component_profile_keywords` lazy properties
- `SQLTranslationContext` — all runtime state; the only thing passed between translation phases
- `ExprUsage` — LIST / SCALAR / BOOLEAN / EXISTS; drives how expressions are translated
- `RowShape` — PATIENT_SCALAR / PATIENT_MULTI_VALUE / RESOURCE_ROWS / UNKNOWN; drives CTE
  wrapping decisions
- `DefinitionMeta` — shape + resource flag recorded for each translated define
- `ColumnDefinition` — column name, FHIRPath paths, UDF name, SQL type, is_choice_type flag
- `SQLRetrieveCTE` — placeholder for a retrieve CTE before it is built and named

See `DESIGN.md` for full detail on ExprUsage rules, RowShape determination, and the three
translation phases. See `TECHNICAL_SPECIFICATION.md` for SQL pattern reference.
