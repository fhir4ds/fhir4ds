# QA Handoff — CQL-04 SKEPTIC (CQL 1.5 logical operators)

## Verdict: CLEAN — 6/6 truth-table groups, 0 parity diffs, values correct

Full and/or/xor/implies/not tables over true/false/null (population surface renders
null as False per the pinned null≡false-for-membership doctrine; expression-level
3VL separately guarded); implies semantics verified (null→T=T, null→F=fall, F→null=T,
T→null=fall); resource-backed compositions (active∧/∨/¬, gender=male→active with
p2 F→anything=T).

Evidence: .temp/qa/speccomp2/cql04_skeptic_probe1.py
