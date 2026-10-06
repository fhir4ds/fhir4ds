import { useCallback, useEffect, useState } from "react";
import type { HttpTransport } from "./http-transport";
import type { ValueSetInfo } from "./transport";

/**
 * ValueSet table editor (v3 Slice 1): concepts grid over compose.include.
 * The display column is greyed out — it is ignored for evaluation logic.
 * Saving edits WRITES the workspace valueset file and sets the kernel
 * staleness flag (amber badge + restart hint until restart).
 */
export function ValueSetPane({
  transport,
  path,
  onStaleChange,
  onInsertDeclaration,
}: {
  transport: HttpTransport;
  path: string;
  onStaleChange: (stale: boolean) => void;
  onInsertDeclaration?: (decl: string) => void;
}) {
  const [info, setInfo] = useState<ValueSetInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Row-level draft edits (system/code) keyed by index.
  const [drafts, setDrafts] = useState<Record<number, { system: string; code: string }>>({});

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
      {error && <div className="dev-vserror">{error}</div>}
      {info && (
        <div className="dev-vsmeta">
          <span className="dev-vsurl" title={info.url ?? ""}>
            {info.url ?? "(no url)"}
          </span>
          {onInsertDeclaration && info.url && (
            <button
              className="dev-vsdecl"
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
          Used by: {info.used_by.map((u) => (
            <span key={u} className="dev-vsusedchip">{u}</span>
          ))}
        </div>
      )}
      {info && info.used_by.length === 0 && (
        <div className="dev-vsusedby">Used by: (no library declarations reference this url)</div>
      )}
    </div>
  );
}
