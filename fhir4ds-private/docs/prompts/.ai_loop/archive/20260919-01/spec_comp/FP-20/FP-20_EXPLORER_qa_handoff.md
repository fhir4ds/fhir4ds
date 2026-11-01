# QA Handoff — FP-20 EXPLORER launch (2026-08-19)

**Chunk**: FHIRPath §9 Environment Variables, §10 Types and Reflection, §11 Type Safety, §12 Formal Specifications.
**Personality**: EXPLORER (boundary-combination fuzzing).
**Probes**: `/mnt/d/fhir4ds/.temp/qa/fp20_explorer2_2026_08_19/probe.py` (81 dual-path cases),
`probe2.py` (23 dual-path cases, contained-resource env vars + CRLF/whitespace),
inline battery (27 dual-path cases, unqualified type specifiers + uri-family fields).
**Total: 131 fresh dual-path (native extension vs forced Python fallback) cases, 0 parity diffs.**

## What was probed (per EXPLORER mandate)

1. **%context/%rootResource original-node invariant under iteration**: `select`, nested
   `select`, `where`, `repeat`, `first()`, deep `contact.name.select(...)` — all return
   the ORIGINAL node on both engines. Also with nested `contained` two levels deep.
2. **%resource/%rootResource with contained resources** (FHIR-spec §9 extension):
   `contained.select(%resource.id)` → outer row resource; `contained.first().contained.select(%rootResource.id)`
   → outer row resource. Spec-correct: %resource is the resource containing the ORIGINAL
   node (%context = row resource), not the navigated focus. NOT A BUG.
3. **Env-var availability/error modes**: `%ucum` (→ UCUM URL), `%sct`, `%loinc` available;
   `%ucum.version` empty; `%terminologies`/`%environment` undefined → empty with clear
   "undefined environment variable" error classification (host extension point; no
   terminology service configured — FHIR-spec-added vars, not base §9 mandates);
   `environment()` is not a FHIRPath function → empty + unknown-function warning,
   consistent; `%nosuchvar`, `%\`nosuchvar\``, `%'nosuchvar'` all identical; `%\`context\``
   and `%\`ucum\`` backtick forms work.
4. **type() on primitive families incl. uri-family chains**: canonical (meta.profile),
   uri (meta.source, identifier.system, attachment.url, urn:uuid/urn:oid systems), code
   (contentType, status), string, integer (size), instant (meta.instant), date, boolean,
   id, HumanName.family. HISTORIAN's Meta.profile→canonical / Meta.source→uri fix
   re-verified intact.
5. **is/as on uri-family members**: `is FHIR.uri` true through canonical→uri chain,
   `is FHIR.canonical` exact true, `as(FHIR.uri)`/`as(FHIR.canonical)` pass-through,
   `as(FHIR.string)`/`as(FHIR.uuid)` empty. `is string`/`as string` asymmetry
   (`status is string` → true, `status.as(string)` → empty) re-confirmed as the
   FP-15 HISTORIAN fixture-pinned doctrine (official R4 fixtures pin `as`/`ofType`
   EXACT for primitives; fixtures outrank 2018Sep §6.3 prose which is subtype-inclusive).
   Unqualified type specifiers (`is uri`, `as code`) work on both engines.
6. **Reflection through tuple literals**: `{a: 1}` etc. are SYNTAX ERRORS — verified
   against the official grammar: `literal : '{' '}'` (null literal only); NO tuple
   production exists in 2018Sep OR N1. The launch-note supposition "tuple literals ARE
   in the grammar" is incorrect. Consistent with HISTORIAN's `{1,2}` pin. NOT A BUG.
7. **§11 type-safety error surfaces through parents**: `(1 = 'a')` empty through
   `and`/`or`/`not()`/`implies`/`= `/`iif` (iif returns else-branch); `1 + 'a'` error
   surfaces as empty through `|`, `combine()`; `('a' < 1) implies true` empty;
   `5 'cm' = 5 'kg'` empty (incompatible units). All parity-clean.
8. **§12 grammar oddities**: 6-deep nested parens, `%\`backtick\`` env vars,
   `\uXXXX` escapes, CR/LF/TAB inside expressions through DuckDB SQL strings,
   whitespace around `.`, `select`, `(`, `)` — all parsed identically on both engines.

## Findings

**Zero CRITICAL/HIGH/MEDIUM findings. Three LOW informational pins (all INTENDED):**
- QA-E1 (LOW, INTENDED): `as()` exact-match asymmetry vs subtype `is()` — FP-15
  fixture-pinned doctrine, reconfirmed on uri-family members and unqualified specifiers.
- QA-E2 (LOW, INTENDED): tuple literals `{a: 1}` rejected — conforms to official grammar.
- QA-E3 (LOW, INTENDED): `%terminologies`/`%environment` undefined without a configured
  terminology service — host extension point; error classification consistent.

## Validation

Full conformance run filtered per PROC_VALIDATION context-protection mandate; result
recorded in `.temp/qa/fp20_explorer2_2026_08_19/conformance_summary.log` (see
engineer_handoff.md for final counts — run executed during QA/FIX transition).

**Recommendation: CLEAN exit — third consecutive clean personality launch on FP-20;
chunk should CLOSE.**
