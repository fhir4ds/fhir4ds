# QA Handoff - CQL-02 HISTORIAN

Fresh independent HISTORIAN audit focused on CQL clinical types: `Code`, `CodeSystem`, `Concept`, `ValueSet`, and `Vocabulary`. Archived `spec_comp/**` outputs were not used.

Finding `CQL02-HIST-001`: clinical values lost type identity when carried through definitions. `Code`/`Concept`/`ValueSet`/`CodeSystem` constructors and named terminology references could be materialized as generic resource rows, strings, or identifiers; downstream `is`/`as` checks fell into FHIR `resourceType` probing or SQL binder errors. Reproducer included `DirectCode is Code`, `DirectVS is Vocabulary`, and named ValueSet aliasing.

Follow-on regression during remediation: DQM fluent membership functions received structured ValueSet JSON where `in_valueset(resource, path, url)` expects a canonical URL. CMS71 dropped to 10.8% before the fluent ValueSet argument normalization was added.

Spec basis: CQL 1.5.3 Appendix B defines `ValueSet` and `CodeSystem` as structured `Vocabulary` subtypes with `id`, optional `version`, and `name`; `as` is an assertion and `is` is a type test. Terminology membership still identifies external value sets by canonical id/url.
