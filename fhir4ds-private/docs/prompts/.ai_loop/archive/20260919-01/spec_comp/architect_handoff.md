# Architect Handoff — CQL-13 (EXPLORER), iteration 1

Scope audited: this launch's deltas (udf/datetime.py duration uncertainty,
extensions/cql/src/cql_extension.cpp CqlDurationBetweenString mirror,
translator/expressions/_temporal_components.py constructors, parity tests),
against the standing golden invariants (dual-engine lockstep, no silent
fallbacks, translator layering, spec-grounded temporal semantics).

Findings:
1. Dual-engine lockstep HELD: the year/month certainty rule and the
   date-only midnight convention are implemented in both engines with
   comments cross-referencing each other, and locked by dual-engine parity
   tests (py-only vs cpp connections asserted equal). Extension redeployed
   and md5-verified across build/bundle/site-packages.
2. No silent fallbacks introduced: the only except-to-null path
   (cqlDurationBetween wrapper) is pre-existing; the new ValueError for the
   §22.5 DateInvalid interior-null form fails fast at translation time.
   The DateTime(null) fixture regression during the fix loop was caught by
   the master gate (1704→1706) and root-caused (all-null vs null-above-
   specified distinction) rather than special-cased.
3. Layering intact: constructor semantics changed only in the translator
   layer; duration semantics only in the UDF layer; no SQLRaw or
   cross-boundary SQL construction added.
4. One corrected test expectation (DurationMonthsAsymmetric 18→19) was
   an arithmetic error in the pinned comment, produced by the phantom
   23:59:59.999 boundary; now spec-verified and documented in-test.
5. Follow-up (logged, not blocking): CalculateAge* UDFs still return crisp
   values for partial birthDates (documented day-1 convention); unifying
   them with cqlDurationBetween uncertainty belongs to the age-functions
   chunk. Also the uncertainty-interval JSON convention remains
   duplicated between Python and C++ (pre-existing accepted duplication).

No RETRY_QA. Audit verdict: PASS. Recommend clean exit.
