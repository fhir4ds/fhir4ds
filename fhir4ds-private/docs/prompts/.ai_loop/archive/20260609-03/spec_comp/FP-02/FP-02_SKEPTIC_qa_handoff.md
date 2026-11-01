# QA Handoff: FP-02 SKEPTIC

Scope: FHIRPath §4.2 operators, §4.3 function invocations, §4.4 null/empty propagation, and §4.5 singleton evaluation.

Spec grounding:
- §4.3: functions operate on collections, constants are converted to singleton collections, and fluent dot invocation chains functions.
- §4.4: missing or null physical members have no node; `{ }` is the empty collection; single-input functions/operators generally propagate empty operands, while collection-taking operations treat empty as a collection.
- §4.5: a single-item collection may be implicitly converted for singleton inputs; multi-item collections signal an error; singleton non-Boolean values can evaluate to `true` only when the expected input type is Boolean.
- §6.8, referenced from §4.2 operations, orders `is/as` above `|`.

Hypotheses tested:
- Native parser may bind `is/as` too loosely relative to union.
- Dot invocation should bind tighter than arithmetic.
- Empty propagation should differ only where the spec says collection operators/functions take collections.
- Multi-item singleton operands should fail through public row-resilience consistently.
- Underlying JSON null should behave as no node.

Results:
- `QA-001` MEDIUM opened: native C++ parses `1 | 2 is Integer` and `1 | 'a' as String` as if `is/as` bind below union, returning empty and `fhirpath_is_valid=false`; forced Python fallback returns the spec-shaped valid union results.
- `QA-002` LOW opened: native `names.trim()` accepts a multi-item string collection and trims the first item, while forced fallback returns empty through row resilience. This is an extension-surface parity issue grounded in the §4.5 singleton rule.
- Other probes passed native/fallback parity: dot invocation precedence (`4+5.count()`), `(4+5).count()`, empty propagation for `+`, `&`, `|`, `count()`, `empty()`, Boolean singleton row resilience, multi-item substring argument handling, and JSON null navigation.

Evidence:
- Probe script: `.temp/qa/fp02_skeptic/probe_fp02.py`
- Output: `.temp/qa/fp02_skeptic/probe_before.log`

Recommended remediation:
- Reorder the native C++ parser so precedence is `additive -> is/as -> union -> comparisons/equality -> in/contains -> and -> xor/or -> implies`.
- Add native/fallback parity tests for `1 | 2 is Integer`, `1 | 'a' as String`, and a parenthesized control.
- Add a native `trim()` multi-item guard or otherwise align its singleton handling with fallback.
