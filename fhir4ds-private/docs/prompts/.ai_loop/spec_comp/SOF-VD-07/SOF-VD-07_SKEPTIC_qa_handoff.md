# QA Handoff — SOF-VD-07 SKEPTIC (select.repeat)

## Verdict: CLEAN — 11/11 fresh dual-path cases (flagged=0 after 4 adjudications)

Verified: repeat single path recursive traversal to ANY depth (1, 1.1, 1.2,
1.2.1, 2); repeat + nested select composition; MULTIPLE repeat paths combined
via UNION semantics (value-dedup — every node once); duplicate values collapse
(three 't' nodes -> one row); columns evaluated per repeated node context;
absent path -> no rows; %rowIndex per-emitted-row counter; repeat+forEach ->
typed ParseError (SD: at most one row generator — verified typed message).

4 adjudications (all want errors, parity OK): (1) norm() int-normalizes '1'->1
(want formatting); (2) primitive-yielding repeat paths (item.linkId) return
EMPTY on both engines — documented INTENT (repeat collects only complex/dict
elements; SOF-VD-05 HISTORIAN doctrine; no official fixture pins otherwise);
(3) harness table name: default generator uses pluralized per-type tables —
probes must use SQLGenerator(source_table='resources').

Evidence: .temp/qa/speccomp2/sofvd07_skeptic_probe1.py
