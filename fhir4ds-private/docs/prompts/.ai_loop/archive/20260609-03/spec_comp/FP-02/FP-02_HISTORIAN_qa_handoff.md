# QA Handoff - FP-02 HISTORIAN

Status: CLEAN

Scope: FHIRPath N1 §4.2 Operators, §4.3 Function Invocations, §4.4 Null and Empty, and §4.5 Singleton Evaluation of Collections.

Spec grounding:
- §4.2 defines operator examples for math, Boolean implication, union, and string addition, with detailed behavior delegated to Operations.
- §4.3 states that functions operate on input collections, may take expression arguments, constants are first converted to singleton collections, and fluent chaining is expected.
- §4.4 states missing or null members produce empty collections, not a null literal, and §4.4.1 says single-input functions/operators propagate empty while collection operators such as union treat empty as an ordinary collection.
- §4.5 defines singleton evaluation: one convertible node is used, one non-Boolean node in a Boolean context evaluates true, empty remains empty, and larger collections signal an error.
- §6.8 gives precedence: dot invocation, indexer, unary, multiplicative, additive, `is/as`, union, comparison, equality, membership, `and`, `xor/or`, `implies`.

Probe:
- Created `.temp/qa/fp02_historian_probe.py`.
- Ran isolated native and forced Python fallback subprocesses to avoid extension registration bleed-through.
- Covered 24 cases across math/comparison, implication, union, additive string use, `is/as` precedence, multiplicative/additive precedence, left-associative `or/xor`, function calls vs navigation without `()`, chained filter/projection, collection-valued function arguments, missing path/null navigation, empty propagation, documented `count()`/`empty()` exceptions, and singleton Boolean/function/operator errors.

Result:
- Native C++ extension loaded: true.
- Forced Python fallback loaded native extension: false.
- Native expectation failures: 0.
- Fallback expectation failures: 0.
- Native/fallback mismatches: 0.

Issues logged: none.

Evidence:
- `.temp/qa/fp02_historian_probe.log` reports `case_count: 24`, no failures, and no backend mismatches.
