import { useCallback, useEffect, useState } from "react";
import type { HttpTransport } from "./http-transport";
import type { ResolutionRow, TerminologyImportResult, TerminologyPreviewResult, ValueSetInfo } from "./transport";

/**
 * ValueSet table editor (v3 Slice 1): concepts grid over compose.include.
 * The display column is greyed out — it is ignored for evaluation logic.
 * Saving edits WRITES the workspace valueset file and sets the kernel
 * staleness flag (amber badge + restart hint until restart).
 *
 * VSAC/terminology integration (c-vsac-cleanroom): an Import row lets the
 * author expand a remote ValueSet by URL/OID (Preview shows codes+count),
 * then save it as a LOCAL workspace file with provenance. Imported sets are
 * ordinary local files afterwards (normal stale/restart contract).
 */
export function ValueSetPane({
  transport,
  path,
  onStaleChange,
  onInsertDeclaration,
  onImported,
}: {
  transport: HttpTransport;
  path: string;
  onStaleChange: (stale: boolean) => void;
  onInsertDeclaration?: (decl: string) => void;
  onImported?: () => void;
}) {
  const [info, setInfo] = useState<ValueSetInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Row-level draft edits (system/code) keyed by index.
  const [drafts, setDrafts] = useState<Record<number, { system: string; code: string }>>({});
  // Terminology import state.
  const [importUrl, setImportUrl] = useState("");
  const [preview, setPreview] = useState<TerminologyPreviewResult | null>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [resolutions, setResolutions] = useState<ResolutionRow[]>([]);
  // Provenance for the last successful preview/import (persists after import).
  const [provAt, setProvAt] = useState<Date | null>(null);
  const [provCount, setProvCount] = useState<number | null>(null);
  const [insertAttn, setInsertAttn] = useState(false);

  const reload = useCallback(async () => {
    setError(null);
    try {
      const r = await transport.valueset(path);
      setInfo(r);
      setDrafts({});
      onStaleChange(r.stale);
    } catch (e) {
      setInfo(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [transport, path, onStaleChange]);

  useEffect(() => {
    reload().catch(() => {});
  }, [reload]);

  useEffect(() => {
    let alive = true;
    transport
      .terminologyResolution()
      .then((r) => {
        if (alive) setResolutions(r.resolutions ?? []);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [transport]);

  const doPreview = useCallback(async () => {
    setError(null);
    setImportMsg(null);
    setInsertAttn(false);
    setBusy(true);
    try {
      const r = await transport.terminologyPreview(importUrl);
      setPreview(r);
      setProvAt(new Date());
      setProvCount(r.count ?? r.concepts?.length ?? 0);
    } catch (e) {
      setPreview(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [transport, importUrl]);

  const doImport = useCallback(async () => {
    setError(null);
    setImportMsg(null);
    setBusy(true);
    try {
      const r = await transport.terminologyImport(importUrl);
      const stem = (r.path ?? "").split("/").pop()?.replace(/\.json$/, "") ?? "";
      setImportMsg(
        `Saved ${stem || r.path}.json — click Insert to add to header`,
      );
      setProvCount(r.code_count ?? provCount ?? 0);
      setProvAt((d) => d ?? new Date());
      onStaleChange(true);
      onImported?.();
      setInsertAttn(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [transport, importUrl, onStaleChange, onImported, provCount]);

  const runEdit = useCallback(
    async (edit: {
      action: string;
      system?: string | null;
      code?: string | null;
      display?: string | null;
      old_code?: string | null;
    }) => {
      setBusy(true);
      setError(null);
      try {
        const r = await transport.valuesetEdit(path, edit);
        setInfo(r);
        setDrafts({});
        onStaleChange(true);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [transport, path, onStaleChange],
  );

  const concepts = info?.concepts ?? [];
  const name = path.split("/").pop() ?? path;

  return (
    <div className="dev-vspane">
      <div className="dev-toolbar">
        <span className="dev-pane-label">ValueSet</span>
        <span>{name}</span>
        {info?.stale && (
          <span className="dev-stale" title="Terminology changed on disk — restart the kernel to reload it, then re-run tests">
            ⚠ Valueset changed — Restart kernel to reload
          </span>
        )}
        <button disabled={busy} onClick={() => runEdit({ action: "add", system: "http://loinc.org", code: "NEW-CODE" })}>
          + concept
        </button>
        <button disabled={busy} onClick={reload}>
          Reload
        </button>
      </div>
      <div className="dev-vsimport">
        <input
          className="dev-vsurlinput"
          placeholder="ValueSet URL or OID…"
          value={importUrl}
          onChange={(e) => setImportUrl(e.target.value)}
        />
        <button disabled={busy || !importUrl} onClick={doPreview} title="Expand the remote ValueSet (no disk writes)">
          Preview
        </button>
        <button
          disabled={busy || !importUrl}
          onClick={doImport}
          title="Import as a local workspace valueset file (with provenance); sets the stale-terminology flag"
        >
          Import
        </button>
        {importMsg && <span className="dev-vsimportmsg">{importMsg}</span>}
      </div>
      {(provCount !== null || preview) && provAt && provCount !== null && (
        <div className="dev-vsprov">
          {provCount} concepts from VSAC — OID{" "}
          {importUrl.split("/").filter(Boolean).pop() ?? importUrl} — retrieved{" "}
          {provAt.toLocaleString()}
        </div>
      )}
      {preview && (
        <div className="dev-vspreview">
          <div className="dev-vspreview-head">
            {preview.url ?? importUrl} — {preview.count} codes
          </div>
          {(preview.concepts ?? []).slice(0, 5).map((c, i) => (
            <div key={i} className="dev-vspreview-row">
              {c.system} | {c.code}
            </div>
          ))}
          {(preview.concepts?.length ?? 0) > 5 && (
            <div className="dev-vspreview-more">
              +{(preview.concepts?.length ?? 0) - 5} more
            </div>
          )}
        </div>
      )}
      {error && <div className="dev-vserror">{error}</div>}
      {info && (
        <div className="dev-vsmeta">
          <span className="dev-vsurl" title={info.url ?? ""}>
            {info.url ?? "(no url)"}
          </span>
          {onInsertDeclaration && info.url && (
            <button
              className={"dev-vsdecl" + (insertAttn ? " dev-vsdecl-attn" : "")}
              title={`Insert  valueset "<name>": '${info.url}'  into the open library header`}
              onClick={() => {
                // Declared name: prefer the name used by referencing libraries
                // (used_by chips look like "Demographics.BPVS"), else the file stem.
                const used = info.used_by[0] ?? "";
                const declared = used.includes(".") ? used.split(".").slice(1).join(".") : "";
                const name = declared || (path.split("/").pop() ?? "VS").replace(/\.json$/, "");
                onInsertDeclaration(`valueset "${name}": '${info.url}'`);
              }}
            >
              Insert declaration into header
            </button>
          )}
        </div>
      )}
      <div className="dev-vsgrid">
        <div className="dev-vsrow dev-vshead">
          <span title="Code system URI (http/https)">system</span>
          <span>code</span>
          <span title="Display is documentation only — ignored for evaluation logic">display</span>
          <span />
        </div>
        <div className="dev-vshint">display is ignored for membership — only system + code matter</div>
        {concepts.length === 0 && (
          <div className="dev-vsempty">No concepts in compose.include.</div>
        )}
        {concepts.map((c, i) => {
          const draft = drafts[i] ?? { system: c.system, code: c.code };
          const changed =
            draft.system !== c.system || draft.code !== c.code;
          return (
            <div key={i} className="dev-vsrow">
              <input
                className="dev-vssystem"
                title={draft.system}
                value={draft.system}
                onChange={(e) =>
                  setDrafts((d) => ({ ...d, [i]: { ...draft, system: e.target.value } }))
                }
              />
              <input
                value={draft.code}
                onChange={(e) =>
                  setDrafts((d) => ({ ...d, [i]: { ...draft, code: e.target.value } }))
                }
              />
              <input className="dev-vsdisplay" value={c.display ?? ""} readOnly
                title="Display is documentation only — ignored for evaluation logic" />
              <span className="dev-vsactions">
                <button
                  disabled={busy || !changed}
                  title="Save this row (writes the valueset file; sets the stale-terminology flag)"
                  onClick={() =>
                    runEdit({
                      action: "update",
                      system: draft.system,
                      code: draft.code,
                      old_code: c.code,
                      display: c.display ?? undefined,
                    })
                  }
                >
                  Save
                </button>
                <button
                  disabled={busy}
                  title="Remove this concept from the valueset file"
                  onClick={() =>
                    runEdit({ action: "remove", system: c.system, code: c.code })
                  }
                >
                  ✕
                </button>
              </span>
            </div>
          );
        })}
      </div>
      {info && info.used_by.length > 0 && (
        <div className="dev-vsusedby">
          Used by: {info.used_by.map((u) => {
            const r = resolutions.find((row) => `${row.library}.${row.id}` === u);
            return (
              <span key={u}>
                <span className="dev-vsusedchip">{u}</span>
                {r && (
                  <span
                    className={`dev-reschip dev-reschip-${r.resolved.toLowerCase()}`}
                    title={r.url}
                  >
                    {r.resolved}
                  </span>
                )}
              </span>
            );
          })}
        </div>
      )}
      {info && info.used_by.length === 0 && (
        <div className="dev-vsusedby">
          Used by: (no library declarations reference this url)
          {resolutions.map((r) => (
            <span
              key={`${r.library}.${r.id}`}
              className={`dev-reschip dev-reschip-${r.resolved.toLowerCase()}`}
              title={r.url}
            >
              {r.library}.{r.id}: {r.resolved}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
