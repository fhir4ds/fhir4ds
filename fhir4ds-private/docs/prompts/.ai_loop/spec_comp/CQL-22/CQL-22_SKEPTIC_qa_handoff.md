# QA Handoff — CQL-22 SKEPTIC (Message operator)

## Verdict: CLEAN — 0 defects (11 fresh cases + 2 adjudication re-probes; 0 parity diffs)

Verified: Message generic-over-source passthrough (42 Integer, 3.5 Decimal,
'text-src' String, 100; Trace/Warning/lowercase-trace severities all return
UNMODIFIED source); literal-false AND null conditions fold to bare source
(M3/M4); chained Message outer passthrough (inner Trace -> 1); Coalesce over
Message-with-null-source falls through to 'fallback'; untaken iif branch does
NOT raise (Error severity in dead branch); Message-in-where: Trace severity
returns source (active=true -> IP True; NULL active -> False — fixture
artifact adjudicated live); runtime Error severity RAISES identically on BOTH
engines (err-raise + case-insensitive 'ErRoR' err-case libs — InvalidInputException
'e: error text here' / 'e: row error' verified in where-clause per-row raise).

Adjudications (both probe-expectation errors): (1) M3 want 42 was a typo —
source IS 'text-src' so the fold returns 'text-src'; (2) where-msg fixture
lacked active -> NULL -> False; with active=true seeded, IP=True (live-verified
on native; Error-severity where-row raise also live-verified).

Evidence: .temp/qa/speccomp2/cql22_skeptic_probe1.py
