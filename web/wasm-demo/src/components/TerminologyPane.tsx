/**
 * TerminologyPane (c-wasm-bolton S4): VSAC/UMLS/FHIR terminology import
 * + status, wired to the EXISTING dev-server endpoints via HttpTransport.
 *
 * FDD Q3 resolution (Muse): UMLS key = env-var display ONLY —
 * `UMLS: configured / not configured (UMLS_API_KEY)` + guidance + recheck.
 * Secrets are NEVER written or echoed from the browser.
 */

import { useCallback, useEffect, useState } from "react";
import type { HttpTransport } from "../transport/http-transport";

type TermConfig = {
  provider?: string;
  base_url?: string | null;
  timeout_seconds?: number;
  api_key_env?: string;
};
type TermStatus = { provider: string; configured: boolean; api_key_set?: boolean };
type SearchResult = { system?: string; code?: string; display?: string };

export function TerminologyPane({ transport }: { transport: HttpTransport }) {
  const [config, setConfig] = useState<TermConfig | null>(null);
  const [status, setStatus] = useState<TermStatus | null>(null);
  const [resolution, setResolution] = useState<string[] | null>(null);
  const [importUrl, setImportUrl] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);

  const refresh = useCallback(() => {
    transport.health().then((h: any) => {
      const d = h?.data ?? h;
      setStatus(d?.terminology ?? null);
    }).catch(() => setStatus(null));
    transport.terminologyConfigGet().then((r: any) => {
      const d = r?.data ?? r;
      setConfig(d?.config ?? d ?? null);
    }).catch(() => setConfig(null));
    transport.terminologyResolution().then((r: any) => {
      const d = r?.data ?? r;
      setResolution(d?.valuesets ?? d?.resolved ?? []);
    }).catch(() => setResolution(null));
  }, [transport]);

  useEffect(refresh, [refresh]);

  const runImport = useCallback(
    async (mode: "preview" | "import") => {
      if (!importUrl.trim()) return;
      setBusy(mode);
      setMessage(null);
      try {
        const r =
          mode === "preview"
            ? await transport.terminologyPreview(importUrl)
            : await transport.terminologyImport(importUrl);
        const d: any = (r as any)?.data ?? r;
        if (d?.ok === false) {
          setMessage({ text: d?.diagnostics?.[0]?.message ?? "request failed", error: true });
        } else if (mode === "preview") {
          const n = d?.concept_count ?? d?.concepts?.length ?? "?";
          setMessage({ text: `Preview OK — ${n} concepts${d?.name ? ` (${d.name})` : ""}`, error: false });
        } else {
          setMessage({ text: `Imported → ${d?.path ?? "valuesets/"}`, error: false });
          refresh();
        }
      } catch (e) {
        setMessage({ text: String(e), error: true });
      } finally {
        setBusy(null);
      }
    },
    [importUrl, transport, refresh],
  );

  const runSearch = useCallback(async () => {
    if (!query.trim()) return;
    setBusy("search");
    setResults(null);
    setMessage(null);
    try {
      const r = await transport.terminologySearch(query);
      const d: any = (r as any)?.data ?? r;
      if (d?.ok === false) {
        setMessage({ text: d?.diagnostics?.[0]?.message ?? "search failed", error: true });
      } else {
        setResults(d?.results ?? []);
      }
    } catch (e) {
      setMessage({ text: String(e), error: true });
    } finally {
      setBusy(null);
    }
  }, [query, transport]);

  const umlsKeyEnv = config?.api_key_env ?? "UMLS_API_KEY";
  const umlsReady = status?.api_key_set === true;

  return (
    <div className="term-pane">
      <section className="term-section" aria-label="Terminology status">
        <h4>Status</h4>
        <dl className="term-status">
          <dt>provider</dt>
          <dd>{status?.provider ?? "…"}</dd>
          <dt>VSAC key</dt>
          <dd>{status?.configured ? (status.api_key_set ? "configured" : "not set") : "disabled"}</dd>
          <dt>UMLS</dt>
          <dd>
            {umlsReady ? "configured" : `not configured (${umlsKeyEnv})`}
          </dd>
        </dl>
        {!umlsReady && (
          <p className="term-hint" role="note">
            Set <code>{umlsKeyEnv}</code> and restart <code>fhir4ds dev</code> to enable
            UMLS search.{" "}
            <button type="button" className="term-recheck" onClick={refresh}>
              recheck
            </button>
          </p>
        )}
      </section>

      <section className="term-section" aria-label="Import ValueSet">
        <h4>Import ValueSet (VSAC / FHIR URL)</h4>
        <input
          className="term-input"
          placeholder="http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1061"
          value={importUrl}
          onChange={(e) => setImportUrl(e.target.value)}
          aria-label="ValueSet canonical URL"
        />
        <div className="term-actions">
          <button type="button" disabled={busy !== null} onClick={() => runImport("preview")}>
            {busy === "preview" ? "…" : "Preview"}
          </button>
          <button type="button" disabled={busy !== null} onClick={() => runImport("import")}>
            {busy === "import" ? "…" : "Import"}
          </button>
        </div>
      </section>

      <section className="term-section" aria-label="UMLS search">
        <h4>UMLS code lookup</h4>
        <input
          className="term-input"
          placeholder="concept name (e.g. myocardial infarction)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="UMLS search query"
        />
        <div className="term-actions">
          <button type="button" disabled={busy !== null || !umlsReady} onClick={runSearch}>
            {busy === "search" ? "…" : "Search"}
          </button>
        </div>
        {results && results.length > 0 && (
          <ul className="term-results" role="list">
            {results.slice(0, 10).map((r, i) => (
              <li key={i}>
                <code>{r.code}</code> {r.display ?? ""}{" "}
                <span className="term-system">{r.system}</span>
              </li>
            ))}
          </ul>
        )}
        {results && results.length === 0 && <p className="term-hint">No matches.</p>}
      </section>

      {resolution && resolution.length > 0 && (
        <section className="term-section" aria-label="Resolved valuesets">
          <h4>Resolved in workspace</h4>
          <ul className="term-results">
            {resolution.slice(0, 20).map((v, i) => (
              <li key={i}>{v}</li>
            ))}
          </ul>
        </section>
      )}

      {message && (
        <p className={`term-message${message.error ? " error" : ""}`} role="status">
          {message.text}
        </p>
      )}
    </div>
  );
}
