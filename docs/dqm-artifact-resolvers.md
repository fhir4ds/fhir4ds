# DQM Artifact Resolvers

`MeasureEvaluator` resolves Measure, Library, and ValueSet artifacts through an
artifact resolver. Path-based calls use `FileArtifactResolver` by default; HAPI
or other FHIR-server workflows should pass an explicit resolver.

## File Resolver

```python
import duckdb
from fhir4ds.dqm import MeasureEvaluator, create_artifact_resolver

conn = duckdb.connect(":memory:")
resolver = create_artifact_resolver(
    "files",
    include_paths=["./cql/includes"],
    valueset_paths=["./terminology/valuesets"],
)

result = MeasureEvaluator(conn).evaluate(
    measure_ref="./Measure-CMS122.json",
    cql_library_path="./CMS122.cql",
    artifact_resolver=resolver,
    parameters={"Measurement Period": ("2025-01-01", "2025-12-31")},
)
```

`valueset_paths` may point to ValueSet JSON files, directories containing JSON
files, or Bundles containing ValueSet resources. A CQL `valueset` declaration
can use either `canonical` or `canonical|version`; versioned declarations are
matched to the corresponding ValueSet `version`.

File-backed ValueSets must contain either an `expansion` element or direct
`compose.include.concept` entries. Filter-only compose rules require expansion
by a terminology server before FHIR4DS can use them locally.

## HAPI Resolver

```python
from fhir4ds.dqm import MeasureEvaluator, create_artifact_resolver

resolver = create_artifact_resolver(
    "hapi",
    hapi_base_url="http://localhost:18080/fhir",
    hapi_headers={"Authorization": "Bearer token"},
    hapi_unversioned_valueset_policy="latest",
)

compiled = evaluator.compile_measure(
    measure_ref="http://example.org/fhir/Measure/CMS122|2025",
    artifact_resolver=resolver,
    patient_scope="target_table",
)
```

The HAPI resolver accepts Measure ids, `Measure/<id>` references, and canonical
URLs. Library references are resolved from `Measure.library` or
`relatedArtifact` dependencies. ValueSets declared in the primary CQL library
and transitive includes are resolved from HAPI by canonical URL and optional
version.

If a HAPI ValueSet does not already contain loadable terminology, the resolver
calls `$expand` using the canonical URL and version. Unversioned references that
match multiple ValueSet resources try candidate versions newest-first and use
the newest loadable or expandable ValueSet. Set
`hapi_unversioned_valueset_policy="error"` to reject ambiguous unversioned
references and require a CQL `version` qualifier or `canonical|version`
reference.

## Public API Shape

The stable extension point is `ArtifactResolver`:

- `resolve_measure(ref)`
- `resolve_library(ref=None, *, measure=None, measure_source_id=None)`
- `resolve_include(alias, version=None)`
- `resolve_valueset(ref)`
- `resolve_valuesets_for_cql(cql_text)`
- `fingerprint()`

`MeasureEvaluator.evaluate()` and `compile_measure()` continue to accept legacy
path arguments. New integrations should prefer `measure_ref` plus an explicit
resolver so artifact storage remains independent from SQL generation.
