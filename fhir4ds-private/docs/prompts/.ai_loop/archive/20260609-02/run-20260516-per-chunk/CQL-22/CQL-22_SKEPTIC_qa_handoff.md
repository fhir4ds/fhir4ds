# QA Handoff - CQL-22 SKEPTIC

Spec checked: CQL v1.5.3 Appendix B Message operator and Developer's Guide typing/function resolution rules.

Hypotheses probed:
- Dynamic severity expressions might be optimized away instead of evaluated at runtime.
- Direct CQLMessage might not preserve generic source type T.
- Condition null/false should suppress Error severity.
- Warning/Message/Trace severities should continue and return source.
- Boolean/string/numeric direct SQL condition coercions might diverge between forced Python and native-loaded registrations.

Findings:
- QA-001 HIGH: Message with severity supplied by a parameter or definition evaluating to 'Error' translates to the bare source and does not raise.
- QA-002 MEDIUM: Direct CQLMessage is registered as a Python string-returning UDF, so numeric sources become VARCHAR and Boolean sources fail conversion even when no message is generated.

Fresh validation performed: targeted Python script against current source, forced Python fallback registration, and native-loaded DuckDB registration. No archived spec_comp outputs were used.
