# QA Handoff - FP-20 HISTORIAN

Status: QA found three actionable FHIRPath §10 reflection/type-safety defects and no remaining open issue after remediation.

Fresh probe scope:
- Native DuckDB extension path through `register_fhirpath`.
- Forced Python fallback path by disabling native extension version matching.
- Public surfaces: `fhirpath`, `fhirpath_text`, `fhirpath_json`, `fhirpath_bool`, `fhirpath_number`, and `fhirpath_is_valid`.
- Coverage included `%context`, `%resource`, `%rootResource`, external variables, quoted/backtick variable names, undefined variables, `type()`, `is`, `as`, namespace/type names, supertypes, invalid type specifiers, URI/media type shape, multi-item reflection, and malformed grammar.

Issues verified:
- `QA-FP20-HIST-001`: Native reflection missed Reference and uri metadata.
- `QA-FP20-HIST-002`: Native `type()` reflected only the first collection item.
- `QA-FP20-HIST-003`: Media-type `contentType` reflected as string instead of code, and fallback missed `uri -> string` primitive compatibility.

Non-actionable observations:
- Invalid grammar and invalid type specifier cases remained rejected or row-resilient depending on wrapper strictness.
- Some error-message shapes differ between native and fallback on invalid expressions, but accepted public value surfaces now match for the probed FP-20 cases.
