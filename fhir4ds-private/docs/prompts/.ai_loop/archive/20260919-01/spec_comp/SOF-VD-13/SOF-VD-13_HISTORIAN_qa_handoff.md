# QA Handoff — SOF-VD-13 (HISTORIAN, iteration 1, 2026-08-24)

Chunk: SQL-on-FHIR v2 ViewDefinition — CanonicalResource/DomainResource inheritance,
cnl-0/cnl-1 invariants, tag.name namespace, extra_fields mechanics.

## Spec verification (fetched fresh, not assumed)
- FHIR/sql-on-fhir-v2 repo, `input/resources/viewdefinition/StructureDefinition-ViewDefinition.xml`,
  element `ViewDefinition.url`: constraint cnl-1 declared with
  `<severity value="warning"/>`, source MetadataResource. The OFFICIAL SD pins
  WARNING severity on ViewDefinition.url itself — not just the base CanonicalResource.
- sql-on-fhir.js v2.0.0 (FHIR/sql-on-fhir.js, cloned) `src/validate.js`: `url` is a
  plain `{type:'string'}` in the JSON schema — the reference implementation does not
  enforce cnl-1 at all (neither error nor warning).
- build.fhir.org/canonicalresource.html: cnl-0 WARNING, cnl-1 WARNING.
- RI constant resolution (`src/path.js`): `Object.assign(context, envVars)` — builtin
  env variables override same-named constants (builtin wins).

## Probes (in /mnt/d/fhir4ds/.temp/qa/sof_vd13_historian/, probe1.py)
1. cnl-1 SEVERITY ADJUDICATION (QA-001, MEDIUM): fhir4ds rejects url containing
   `|`/`#`/space with a typed ParseError. The official SD severity is WARNING; the
   sibling cnl-0 invariant is warning-only in fhir4ds; the RI does not check. Under
   fixtures/SD-outrank-prose and internal reference-consistency, `|` and `#` in url
   must be a warning. Whitespace stays a lexical `uri`-type error (`^\S*$`), which is
   independent of cnl-1.
2. extra_fields multi-round-trip: parse -> to_dict -> parse -> to_dict is stable;
   text.div (XHTML xmlns + entities &amp; &#233;) preserved byte-identically;
   dataclass mutations to extra_fields (nested status change, added customKey)
   propagate through to_dict and re-parse. PASS.
3. tag.name namespace warning: returned by validate_view_definition (not the
   warnings module), fires once per tag occurrence, no dedup, deterministic across
   calls; namespaced names do not warn. Acceptable per-occurrence semantics.
4. Unknown-key boundary: root unknown keys preserved verbatim (extra_fields) while
   select/column unknown keys are rejected with typed ParseErrors — consistent with
   the documented §G-3 doctrine (DomainResource inheritance at root only; RI schema
   itself uses additionalProperties:false but lacks DomainResource elements entirely).
5. Constant/builtin shadowing: constants named `resource`/`rowIndex`/`ucum` lose to
   builtins at execution — matches RI `Object.assign(context, envVars)` builtin-wins
   order. No divergence.

## Issue
- QA-001 (MEDIUM, OPEN): cnl-1 on ViewDefinition.url enforced as parse ERROR;
  official SD severity is WARNING and the RI does not check. Fix: demote `|`/`#`
  rejection to a warning in validate_view_definition; keep whitespace rejection as
  a uri lexical error; keep empty/non-string as errors.

## NOT A BUG registry additions
- Builtin variables take precedence over same-named constants at execution
  (matches RI envVars-override order).
- tag.name namespace warnings are per-occurrence with no dedup (deterministic).
