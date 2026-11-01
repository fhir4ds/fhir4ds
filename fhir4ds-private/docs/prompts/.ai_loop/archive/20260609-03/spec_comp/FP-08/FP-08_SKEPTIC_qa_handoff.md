# QA Handoff: FP-08 SKEPTIC

State: QA complete, remediation required.

Spec grounding:
- HL7 FHIRPath N1 §5 says function arguments with required singleton typed parameters signal an error when the argument is multi-item or not of the required type.
- §5.5 conversion functions operate on singleton input collections; multi-item input signals an error.
- §5.5.7 signatures are `toQuantity([unit : String])` and `convertsToQuantity([unit : String])`.
- §5.5.8 signatures are `toString()` and `convertsToString()`.
- §5.5.9 signatures are `toTime()` and `convertsToTime()`.
- §4.1.6 says FHIRPath Time values do not have timezone offsets, so timezone-suffixed time strings were treated as invalid for this run despite the copied format text in §5.5.9.

SKEPTIC source-first hypotheses:
- Native evaluator dispatch might ignore extra arguments for FP-08 converters.
- Forced Python fallback registry might still allow old global or one-argument `convertsToString`/`convertsToTime` convenience forms.
- Native Quantity optional-unit handling might coerce non-String or multi-item unit arguments through `toString()`.
- Quantity parser and Time parser might diverge across native and fallback for malformed strings and partial precision.

Probe:
- Script: `.temp/qa/fp08_skeptic_probe.py`
- Output: `.temp/qa/fp08_skeptic_probe_before.json`
- Native extension loaded: true
- Forced fallback loaded: false, as intended
- Cases: 35

Findings:
- `QA-001` MEDIUM: native `toQuantity([unit])` / `convertsToQuantity([unit])` do not enforce exact 0/1 arity or String singleton unit arguments. Native accepts `1.toQuantity('1','g')`, `1.convertsToQuantity('1','g')`, `1.toQuantity(1)`, `1.convertsToQuantity(1)`, and multi-item unit args.
- `QA-002` MEDIUM: FP-08 zero-arg converters accept invalid argument/global forms. Native accepts `s.toString(1)` and `time_min.toTime(1)`; both backends accept `s.convertsToString(1)`; forced fallback accepts `convertsToString(s)` and `convertsToTime(time_min)`.
- `QA-003` MEDIUM: forced Python fallback `toString()` and `convertsToQuantity()` do not raise singleton errors for constant multi-item inputs, so `fhirpath_is_valid('(1|2).toString()')` and `fhirpath_is_valid('(1|2).convertsToQuantity()')` are true.

Non-findings:
- Partial time strings `14`, `14:30`, `14:30:59`, and `14:30:59.123` matched across backends.
- Invalid time ranges and timezone-suffixed time strings returned empty/false across backends.
- Malformed Quantity strings such as an unterminated quoted unit returned empty/false across backends.
