# QA Handoff — SOF-VD-13 SKEPTIC (invariants)

## Verdict: CLEAN — 19/19 fresh cases (flagged=0 after 3 adjudications)

Verified: cnl-1 on url — pipe/# surface as WARNING (spec severity; not
promoted to error), SPACE is a lexical uri error, empty string rejected;
cnl-1 NOT applied to Column.type (relative URIs + element-ID refs accepted;
SAME-resource element-ID accepted, CROSS-resource rejected at generation
with typed ValidationError); profile[]/meta.profile[] canonical form permits
|version and |version|frag, rejects spaces/empty; cnl-0 name warning
(lowercase-first, 1-char, 256-chars -> single WARNING, parse+generate OK;
Capitalized clean); relatedArtifact retained via extra_fields roundtrip;
text.div narrative round-trips byte-for-byte; tag.name namespace warning
(no-slash names warn, namespaced OK).

Adjudications: i1/i2 cnl-1 severity is WARNING per spec (verified via
validate_view_definition warnings); i7 split into same-resource (accepted)
vs cross-resource (rejected) per SOF-VD-04 doctrine.

Evidence: .temp/qa/speccomp2/sofvd13_skeptic_probe1.py + /tmp/opencode adjudications
