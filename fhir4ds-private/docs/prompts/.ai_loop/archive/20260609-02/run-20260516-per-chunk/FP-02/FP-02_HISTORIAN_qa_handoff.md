# QA Handoff - FP-02 HISTORIAN

Scope: FHIRPath sections 4.2 Operators, 4.3 Function Invocations, 4.4 Null and Empty Propagation, and 4.5 Singleton Evaluation of Collections.

Spec checked: HL7 FHIRPath Normative Release sections 4.2, 4.3, 4.4.1, 4.5, and 5.5.1. Key normative points used: functions operate on collections and can be chained; constants invoked as function inputs are singleton collections; single-input functions/operators generally propagate empty; collection-input operators like union treat empty as an ordinary empty collection; singleton Boolean evaluation converts a single non-Boolean node to true when Boolean input is expected; multi-item singleton inputs signal an error.

Fresh probes performed:
- Compared native C++ DuckDB extension registration against forced Python fallback registration for 56 expressions covering `&`, `+`, `in`, `contains`, `|`, indexing, chained functions, `where`, `select`, missing/null members, `empty`, `count`, `iif`, Boolean operators, and `not()`.
- Confirmed no parity drift for empty-literal operators, collection union with empty, multi-item singleton errors caught by wrappers, null navigation, and non-Boolean singleton Boolean operators.

Finding:
- QA-001 MEDIUM: Python fallback rejects `iif()` criteria that evaluate to a single FHIR node in the non-strict DuckDB wrapper path. Reproducer: `fhirpath_json({"resourceType":"Patient","gender":"female"}, "iif(gender, 1, 2)")`. Native C++ returns `[1]`; forced Python fallback returns NULL/empty. This is a public DuckDB backend parity/API-contract issue, not permission to weaken strict core semantics: official R4 `testIif6` expects a semantic error for literal non-Boolean criteria under strict mode.

Recommended fix:
- Align the Python fallback truthiness helper used by non-strict `iif()` with native wrapper behavior while preserving strict core behavior: empty -> false for `iif` selection, singleton Boolean -> its value, singleton non-Boolean -> true only outside strict mode, multi-item -> `FHIRPathError`.
- Add a DuckDB parity regression that compares native and forced fallback outputs for `iif(gender, 1, 2)`.
