# QA Handoff — FP-19 HISTORIAN (§7.1 + §8)

## Verdict: CLEAN — zero defects (19 fresh cases; 3 MISS all adjudicated probe-expectation errors)

Normative rows verified. Adjudications: (1) iif-min: my hand-transcribed criterion
`... $total != {} or ...` is malformed — `$total = {}`/`!= {}` comparisons are
expected-EMPTY per the {} = {} doctrine, making the iif criterion empty → row-resilient
[]; CANONICAL spelling is `.aggregate(iif($total.empty(), $this, iif($this < $total,
$this, $total)))` → ['1'] (verified). (2) outer-init: id.length()=2 → 2+1+2+3=8 CORRECT
(my want=3 arithmetic error). (3) quoted-div on integers → [] CORRECT (ints have no div
child). All rows engines-identical.

Evidence: .temp/qa/speccomp2/fp19_historian_probe1.py + adjudication probes
