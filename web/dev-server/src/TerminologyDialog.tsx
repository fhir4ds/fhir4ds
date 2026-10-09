import { useCallback, useEffect, useRef, useState } from "react";
import type { Transport } from "./transport";

/** S2 (c-cleanroom-ux5 item 1): in-app VSAC/terminology config dialog.
 *
 * Writes [terminology] to fhir4ds.toml via /api/terminology/config.
 * HARD RULE: the API key is referenced by env var NAME only — the raw
 * key value is never accepted or shown (server rejects unknown fields).
 */
export function TerminologyDialog({
  transport,
  onClose,
  onSaved,
}: {
  transport: Transport;
  onClose: () => void;
  onSaved?: () => void;
}) {
  const [provider, setProvider] = useState("disabled");
  const [baseUrl, setBaseUrl] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState("5");
  const [apiKeyEnv, setApiKeyEnv] = useState("UMLS_API_KEY");
  const [keyResolves, setKeyResolves] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // S6 fix: a late-resolving GET must never clobber user edits (selecting
  // vsac then saving could silently revert to the loaded provider under
  // slow loads; e2e flake + real UX bug). Guarded by an interacted ref set
  // on the FIRST user change to any field.
  const interactedRef = useRef(false);
  const markInteracted = useCallback(() => {
    interactedRef.current = true;
  }, []);
  useEffect(() => {
    let cancelled = false;
    transport
      .terminologyConfigGet()
      .then((r) => {
        if (cancelled || interactedRef.current) return;
        if (r.ok && r.config) {
          setProvider(r.config.provider);
          setBaseUrl(r.config.base_url ?? "");
          setTimeoutSeconds(String(r.config.timeout_seconds));
          setApiKeyEnv(r.config.api_key_env);
          setKeyResolves(r.config.key_env_resolves ?? null);
        } else {
          setErr(r.diagnostics?.[0]?.message ?? "failed to load config");
        }
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [transport]);

  const save = useCallback(async () => {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const timeout = Number(timeoutSeconds);
      const updates: Record<string, unknown> = { provider, api_key_env: apiKeyEnv.trim() };
      if (baseUrl.trim() !== "") updates.base_url = baseUrl.trim();
      if (timeoutSeconds.trim() !== "" && Number.isFinite(timeout) && timeout > 0) {
        updates.timeout_seconds = timeout;
      }
      const r = await transport.terminologyConfigPost(updates);
      if (!r.ok) {
        setErr(r.diagnostics?.[0]?.message ?? "save failed");
        return;
      }
      if (r.config) setKeyResolves(r.config ? null : null);
      const g = await transport.terminologyConfigGet();
      if (g.ok && g.config) setKeyResolves(g.config.key_env_resolves ?? null);
      setMsg("Saved to fhir4ds.toml — endpoints reloaded.");
      onSaved?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [transport, provider, apiKeyEnv, baseUrl, timeoutSeconds, onSaved]);

  return (
    <div className="dev-dialog-backdrop" onClick={onClose}>
      <div className="dev-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dev-dialog-head">
          <span className="dev-pane-label">Terminology settings</span>
          <button className="dev-dialog-x" onClick={onClose} title="Close">✕</button>
        </div>
        {err && <div className="dev-vserror">{err}</div>}
        {msg && <div className="dev-vsimportmsg">{msg}</div>}
        <div className="dev-dialog-body">
          <label className="dev-rblabel" title="Terminology provider (writes [terminology] in fhir4ds.toml)">
            provider
          </label>
          <select className="dev-rbinput dev-rbsel" value={provider} onChange={(e) => { markInteracted(); setProvider(e.target.value); }}>
            <option value="disabled">disabled (local only)</option>
            <option value="vsac">vsac (NLM VSAC)</option>
            <option value="http">http (FHIR R4 server)</option>
          </select>

          <label className="dev-rblabel" title="Optional base URL override (leave empty for provider default)">
            base_url
          </label>
          <input
            className="dev-rbinput"
            placeholder="https://cts.nlm.nih.gov/fhir (default)"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
          />

          <label className="dev-rblabel" title="Request timeout in seconds">timeout_seconds</label>
          <input
            className="dev-rbinput"
            type="number"
            min="0.5"
            step="0.5"
            value={timeoutSeconds}
            onChange={(e) => setTimeoutSeconds(e.target.value)}
          />

          <label
            className="dev-rblabel"
            title="NAME of the environment variable holding the UMLS/VSAC API key — the key value itself is never stored in the toml or shown here"
          >
            api_key_env (env var NAME — never the key)
          </label>
          <input
            className="dev-rbinput"
            placeholder="UMLS_API_KEY"
            value={apiKeyEnv}
            onChange={(e) => setApiKeyEnv(e.target.value)}
          />
          <div className="dev-dialog-hint">
            {keyResolves === true
              ? "✓ the named env var is set in the dev server process"
              : keyResolves === false
                ? "⚠ the named env var is NOT set — set it where the server starts"
                : ""}
          </div>
        </div>
        <div className="dev-dialog-foot">
          <button disabled={busy} onClick={save} title="Persist to fhir4ds.toml [terminology]; applies without restart">
            Save
          </button>
          <button onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
