# QA Handoff - FP-06 HISTORIAN

Scope: FHIRPath §5.5.1 `iif`, §5.5.2 Boolean conversion, and §5.5.3 Integer conversion.

Spec basis checked:
- Official FHIRPath conversion text: Boolean conversion accepts only Boolean, 0/1 integer/decimal, and the specified case-insensitive string table; invalid singleton values return empty/false for `convertsToBoolean`.
- Official FHIRPath integer conversion text: `toInteger()` accepts Integer, Boolean, or strings matching `(+|-)?\d+`; decimals and whitespace-padded strings do not convert.
- Official R4 conformance includes multi-item `('item1' | 'item2').iif(...)` as invalid execution.

Probes run:
- `.temp/qa/fp06_historian_probe.py` compared public native DuckDB UDFs, forced Python fallback registration, direct Python UDF wrappers, and the core evaluator across lazy `iif`, non-strict `iif`, Boolean conversion tables, integer lexical boundaries, and int32 bounds.
- Strict core spot checks verified `iif('non boolean criteria', ...)` raises in strict mode while non-strict DuckDB-facing wrappers remain row-resilient.

Finding:
- `QA-001` (MEDIUM): source/binary drift in native C++ `fn_iif`. Public bundled native and forced-Python UDFs currently return empty/NULL for multi-item `iif` input, but the current C++ source lacked the `input.size() > 1` guard and would evaluate a branch if rebuilt from source.

Recommended remediation:
- Restore the explicit native `fn_iif` input singleton guard before criterion/branch evaluation.
- Add a native SQL regression in `extensions/fhirpath/test/sql/fhirpath.test`.
- Rebuild/copy the bundled extension if the build toolchain is available, then rerun focused parity tests.
