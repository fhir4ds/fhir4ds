import { useCallback, useEffect, useMemo, useState } from "react";
import type { Transport } from "./transport";

/** S2 (c-cleanroom-ux5 item 2): workspace file/dir picker.
 *
 * Browses the SERVER filesystem via /api/fs/list (sandboxed to the
 * workspace root) and persists the chosen path to the [dev] manifest
 * via /api/workspace/add-path, extending the convention-dir discovery.
 */
export function PathPickerDialog({
  transport,
  kind,
  onClose,
  onAdded,
}: {
  transport: Transport;
  kind: "cql" | "valueset" | "measure" | "data" | "view";
  onClose: () => void;
  onAdded?: () => void;
}) {
  const [dir, setDir] = useState<string>("");
  const [entries, setEntries] = useState<{ name: string; kind: "dir" | "file"; suffix: string }[]>([]);
  const [filter, setFilter] = useState("");
  const [manual, setManual] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(
    (p: string) => {
      transport
        .fsList(p || undefined)
        .then((r) => {
          if (r.ok) {
            setDir(r.path);
            setEntries(r.entries);
            setErr(null);
          } else {
            setErr(r.diagnostics?.[0]?.message ?? "listing failed");
          }
        })
        .catch((e) => setErr(String(e)));
    },
    [transport],
  );

  useEffect(() => {
    load("");
  }, [load]);

  const shown = useMemo(() => {
    if (!filter.trim()) return entries;
    const f = filter.trim().toLowerCase();
    return entries.filter((e) => e.name.toLowerCase().includes(f));
  }, [entries, filter]);

  const crumbs = dir && dir !== "." ? dir.split("/") : [];

  const add = useCallback(
    async (rel: string) => {
      setBusy(true);
      setErr(null);
      setMsg(null);
      try {
        const r = await transport.workspaceAddPath(kind, rel);
        if (!r.ok) {
          setErr(r.diagnostics?.[0]?.message ?? "add failed");
          return;
        }
        setMsg(`Added ${r.added} (${r.snapshot?.datasets ?? "?"} datasets, ${r.snapshot?.libraries ?? "?"} libraries after rescan)`);
        onAdded?.();
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [transport, kind, onAdded],
  );

  return (
    <div className="dev-dialog-backdrop" onClick={onClose}>
      <div className="dev-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dev-dialog-head">
          <span className="dev-pane-label">Add {kind} path</span>
          <button className="dev-dialog-x" onClick={onClose} title="Close">✕</button>
        </div>
        {err && <div className="dev-vserror">{err}</div>}
        {msg && <div className="dev-vsimportmsg">{msg}</div>}
        <div className="dev-dialog-body">
          <div className="dev-pickerbar">
            <button
              title="Up one directory (rooted at the workspace)"
              disabled={!crumbs.length}
              onClick={() => load(crumbs.slice(0, -1).join("/"))}
            >
              ↑
            </button>
            <span className="dev-pickerpath" title="current directory (relative to workspace root)">
              /{crumbs.join("/")}
            </span>
            <input
              className="dev-rbinput dev-pickerfilter"
              placeholder="filter…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <div className="dev-pickerlist">
            {shown.map((e) => (
              <div key={e.name} className="dev-pickerrow">
                <span className={e.kind === "dir" ? "dev-pickerdir" : "dev-pickerfile"}>
                  {e.kind === "dir" ? "▸ " : "· "}
                  {e.name}
                </span>
                <span className="dev-pickeractions">
                  {e.kind === "dir" && (
                    <button onClick={() => load(dir === "." ? e.name : `${dir}/${e.name}`)}>open</button>
                  )}
                  <button
                    disabled={busy}
                    title={`Add to the [dev] ${kind} list — discovery picks it up on rescan`}
                    onClick={() => add(dir === "." ? e.name : `${dir}/${e.name}`)}
                  >
                    + add
                  </button>
                </span>
              </div>
            ))}
            {shown.length === 0 && <div className="dev-pickerempty">no entries</div>}
          </div>
          <label className="dev-rblabel" title="Relative to the workspace root, or absolute">
            path
          </label>
          <div className="dev-pickerbar">
            <input
              className="dev-rbinput"
              placeholder="relative/or/absolute/path"
              value={manual}
              onChange={(e) => setManual(e.target.value)}
            />
            <button disabled={busy || !manual.trim()} onClick={() => add(manual.trim())}>
              + add
            </button>
          </div>
        </div>
        <div className="dev-dialog-foot">
          <button onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );
}
