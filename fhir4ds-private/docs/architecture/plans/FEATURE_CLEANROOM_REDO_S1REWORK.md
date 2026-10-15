# REVISED DESIGN NOTE — S1-rework: Terminology per the user's model

**Status**: for conductor review BEFORE implementation (2nd-correction
falsifiability lesson). Supersedes the S1 File>Add dialog surface.
**User contract (verbatim pillars)**: (1) credentials in Settings; (2) runtime
valueset retrieval when a run executes — transparent, cached; (3) UMLS lookup
inside the valueset editor as a building aid.

## 1. Settings surface (pillar 1)

cql-cleanroom HAS a native Settings menu (`DropdownMenu label="Settings"`,
App.tsx:2596, currently Console placement + Recalc cadence). ADD to it:

- **Terminology section** (only when connected — same `/api/mode` handshake):
  - `VSAC API key` — password-type input; stored BROWSER-side (IndexedDB via
    the existing workspace store) per Q2. Written to the server ONLY at call
    time as a request field, never persisted server-side.
  - `FHIR terminology server` — optional base URL override (defaults to
    `https://cts.nlm.nih.gov/fhir`); "other FHIR server" per the user.
  - `UMLS enabled` — read-only status chip fed by the server's key state
    (`api_key_set`); env-var name displayed, never a value (S1 doctrine).
- Settings rows persist in the existing workspace autosave (IndexedDB).

**Server seam (unchanged, reused)**: the dev-server terminology endpoints
take an `api_key` request field; when absent they fall back to the server env
(S1 behavior). The browser key rides the request; nothing is written to disk.

## 2. Runtime valueset retrieval (pillar 2)

- **Hook point — pre-run resolution pass** in the executor: before executing,
  scan the composed library's `valueset "X": <url>` declarations; for each url
  NOT present in the workspace terminology (user-authored overrides win —
  existing precedence), resolve from the configured source via the server
  (`/api/terminology/preview` — expansion) and hydrate into the run's
  terminology set + `cql_valueset_cache_add` bridge (existing
  valuesetBridge.ts path — zero executor redesign).
- **Cache**: IndexedDB store keyed by canonical url (+ version when the
  source supplies one). Entry = expansion concepts + fetchedAt. Hits are used
  without network; misses resolve, then store. No TTL in rework (manual
  refresh: a "clear terminology cache" Settings row); revisit TTL later.
- **Diagnostics**: unresolved valueset at run time → existing run-error
  surface with a typed diagnostic naming the url + configured source
  ("valueset X (url) could not be retrieved from VSAC — check Settings").
  Workspace valuesets keep today's behavior (already resolved).

## 3. UMLS in the valueset editor (pillar 3)

The native ValuesetEditor (`src/components/tabs/ValuesetEditor.tsx`) gains a
**concept search strip**: query input + results list (code/display/system) +
"add to valueset" per row — appends to the compose.include concept list the
editor already manages. Wired to `/api/terminology/search` (UMLS); strip
visible only when connected + UMLS key configured (chip explains otherwise).
No separate menu item.

## 4. Removals from S1

- File>Add "ValueSet from VSAC URL…" and "UMLS concept lookup…" menu items —
  REMOVED (replaced by pillars 1-3).
- The term-dialog modal — REMOVED.
- KEPT: `serverConnection.ts` (handshake + envelope unwrap + terminology
  fetchers — now called from Settings/executor/editor), `/api/mode` port +
  9 pytest, the standalone guard e2e, transport-catch + typed-diagnostics
  patterns.

## 5. Slices

Rework is ONE slice (S1R): Settings rows + pre-run resolution + cache +
editor strip + removals; Muse gate; user checkpoint = user configures a key
in Settings, runs a library with an un-imported valueset url (retrieved
transparently), builds a valueset using UMLS search in the editor.

## 6. Verification

- Standalone: unchanged guard (zero /api/* after probe); Settings shows no
  terminology section (not connected).
- Connected: new e2e — settings persistence; pre-run retrieval with cache
  (second run makes no network call); unresolved-url diagnostic; editor
  search adds a concept. devserver pytest 220 stays green.
