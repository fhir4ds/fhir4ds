# QA Handoff — SOF-VD-13 (SKEPTIC, iteration 1, 2026-08-24)

Chunk: SQL-on-FHIR v2 ViewDefinition — CanonicalResource/DomainResource inheritance,
cnl-0/cnl-1 invariants, sql-name fields, column.tag.name namespace, extra_fields mechanics.

## Spec verification (fetched, not assumed)
- FHIR CanonicalResource (build.fhir.org/canonicalresource.html): cnl-0 WARNING on
  `name`: `name.exists() implies name.matches('^[A-Z]([A-Za-z0-9_]){1,254}$')`;
  cnl-1 on `url`: `exists() implies matches('^[^|# ]+$')`.
- Local v2 SD snapshot (/tmp/sof2/ig/2.0.0/StructureDefinition-ViewDefinition.json):
  contains NO cnl constraints itself (inherited from CanonicalResource) and NO
  relatedArtifact element — confirming the mandate's relatedArtifact.label mention is
  spurious for ViewDefinition (it is an Analytics Layer/Library field).
- ViewDefinition top-level elements enumerated from snapshot (url, identifier, name,
  title, meta, status, experimental, publisher, contact, description, useContext,
  copyright, resource, fhirVersion, constant, select, where + DomainResource base).

## Probes (all in /mnt/d/fhir4ds/.temp/qa/sof_vd13_skeptic/, probe1–3.py)
1. cnl-1 on ViewDefinition.url: `|`, `#`, space, whitespace-only all REJECTED with
   typed ParseError naming cnl-1; clean URLs and %-encoded accepted. MATCHES spec.
   (Enforced as parse ERROR while base-spec severity is WARNING — INTENDED stricter
   boundary, consistent with mandate wording "rejects" and SOF-VD-10 doctrine.)
2. profile[] and meta.profile[]: `url|version` and `url|version|frag` ACCEPTED
   (FHIR canonical form); space and empty-string REJECTED. MATCHES.
3. Column.type keeps the permissive URI check: relative URIs (`Patient.name`),
   absolute system URIs, `Element.x|1.0` accepted; whitespace rejected. cnl-1
   correctly NOT applied there. MATCHES.
4. cnl-0 on ViewDefinition.name: warning-only (never a parse error); 'badlower',
   1-char, 256-char names warn; 'Good_name' does not. Implementation checks
   first-char-upper + 2–255 length instead of the full regex — equivalent because
   the sql-name parse invariant already restricts the charset to ^[A-Za-z][A-Za-z0-9_]*$
   (non-ASCII/space names are rejected before the warning is reachable). Not a bug.
5. sql-name invariant: enforced on ViewDefinition.name, Column.name, Constant.name
   (rejects '1bad', 'bad-name', 'é'). relatedArtifact is not a v2 VD field and is
   preserved verbatim via extra_fields (correct — nothing to sql-name there).
6. column.tag.name namespace: warning fires for 'nonamespace', not for 'ansi/type'.
   Warning severity only. MATCHES §G-4.
7. extra_fields: unknown top-level keys (text, relatedArtifact, purpose,
   experimental) round-trip byte-identical through to_dict; text.div verbatim.
   Dataclass field is repr=False/compare=False — excluded from repr() and equality
   (verified: two VDs differing only in extra_fields compare equal). MATCHES.
8. End-to-end execution: tagged+profiled+meta.profiled VD with constants executes
   in DuckDB; native C++ path and forced Python fallback produce IDENTICAL rows.
9. Gates: viewdef pytest 1238/1238; official ViewDef suite 144/144.

## Issues found
None. Zero CRITICAL/HIGH/MEDIUM/LOW. Clean-exit criteria met at iteration 1
(min_iterations=1).

## NOT A BUG registry additions
- cnl-1 as parse ERROR (stricter than base WARNING severity) — intended.
- cnl-0 warning implemented as first-char+length check, not full regex — equivalent
  under the sql-name precondition.
- relatedArtifact preserved verbatim in extra_fields, unvalidated.
