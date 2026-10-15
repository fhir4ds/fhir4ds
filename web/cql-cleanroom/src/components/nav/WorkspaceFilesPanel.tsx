/**
 * WorkspaceFilesPanel (c-cleanroom-redo S2): server workspace file trees.
 *
 * Connected mode only — lists cql/ valuesets/ measures/ data/ views/ via
 * the EXISTING sandboxed /api/fs/list; file click opens the CQL in the
 * native editor (S2 scope: cql files; other kinds show a JSON preview
 * into the valueset editor when it's a ValueSet). Watcher events over
 * /api/events mark changed files (dot + badge); data-hint surfaces a
 * native banner (locked decision 4: data changes NEVER auto-reload).
 */

import { useCallback, useEffect, useState } from "react";

interface FsEntry {
  name: string;
  kind: "dir" | "file";
  suffix: string;
}

interface WsSnapshot {
  libraries?: { name: string; path?: string; text?: string }[];
  valuesets?: string[];
}

const GROUPS: { dir: string; label: string; suffixes?: string[] }[] = [
  { dir: "cql", label: "CQL Libraries", suffixes: [".cql"] },
  { dir: "valuesets", label: "ValueSets", suffixes: [".json"] },
  { dir: "measures", label: "Measures", suffixes: [".json"] },
  { dir: "data", label: "Data", suffixes: [".ndjson", ".json"] },
  { dir: "views", label: "Views", suffixes: [".json"] },
];

export function WorkspaceFilesPanel({
  connected,
  changedPaths,
  onOpenCql,
  onOpenValuesetJson,
  onAcknowledgedChanges,
}: {
  connected: boolean;
  /** Watcher-marked changed file paths (dot badges). */
  changedPaths: Set<string>;
  onOpenCql: (name: string, text: string) => void;
  onOpenValuesetJson: (name: string, text: string) => void;
  /** S2 Muse MF1: refresh acknowledges (clears) the change badges. */
  onAcknowledgedChanges?: () => void;
}) {
  const [trees, setTrees] = useState<Record<string, FsEntry[]> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const load = useCallback(() => {
    if (!connected) return;
    setError(null);
    Promise.all(
      GROUPS.map((g) =>
        fetch(`/api/fs/list?path=${encodeURIComponent(g.dir)}`)
          .then((r) => r.json())
          .then(
            (
              b: { data?: { ok?: boolean; entries?: FsEntry[] } } & {
                ok?: boolean;
                entries?: FsEntry[];
              },
            ) => {
            const d = b?.data ?? b;
            if (d?.ok === false) {
              return { dir: g.dir, entries: [] as FsEntry[] };
            }
            return { dir: g.dir, entries: d?.entries ?? [] };
            },
          )
          .catch(() => ({ dir: g.dir, entries: [] as FsEntry[] })),
      ),
    ).then((results) => {
      const out: Record<string, FsEntry[]> = {};
      for (const r of results) out[r.dir] = r.entries;
      setTrees(out);
    });
  }, [connected]);

  useEffect(load, [load, nonce]);

  if (!connected) {
    return <div className="nav-empty">connect a server to browse workspace files</div>;
  }

  const openFile = async (group: string, name: string) => {
    try {
      // Server serves file contents only through discovery endpoints;
      // fs/list gives names. CQL text comes from /api/library?name=…
      if (group === "cql" || group === "valuesets") {
        if (group === "cql") {
          const stem = name.replace(/\.cql$/i, "");
          // /api/libraries/<name> carries the full text.
          const res = await fetch(
            `/api/libraries/${encodeURIComponent(stem)}`,
          );
          const b = (await res.json()) as {
            data?: { text?: string };
            text?: string;
          };
          const text = b?.data?.text ?? b?.text;
          if (typeof text === "string") {
            onOpenCql(stem, text);
            return;
          }
          setError(`could not load ${name}`);
          return;
        }
        // valuesets: /api/workspace gives absolute paths for the valueset read.
        const wsRes = await fetch("/api/workspace");
        const wsB = (await wsRes.json()) as {
          workspace?: WsSnapshot;
          data?: WsSnapshot;
        };
        const d: WsSnapshot | undefined = wsB?.workspace ?? wsB?.data;
        const stem = name.replace(/\.json$/i, "");
        const vsPath = (d?.valuesets ?? []).find(
          (p) => String(p).split("/").pop() === name,
        );
        if (vsPath) {
          const res2 = await fetch(
            `/api/valueset?path=${encodeURIComponent(vsPath)}`,
          );
          const b2 = (await res2.json()) as {
            data?: { ok?: boolean; url?: string; concepts?: { system?: string; code?: string; display?: string }[] };
          } & { ok?: boolean; url?: string; concepts?: { system?: string; code?: string; display?: string }[] };
          const d2 = b2?.data ?? b2;
          if (d2?.ok !== false && Array.isArray(d2?.concepts)) {
            const concepts = d2.concepts;
            const bySystem = new Map<string, { code: string; display?: string }[]>();
            for (const c of concepts) {
              const sys = c.system ?? "";
              if (!bySystem.has(sys)) bySystem.set(sys, []);
              bySystem.get(sys)!.push({ code: c.code ?? "", display: c.display ?? "" });
            }
            const vs = {
              resourceType: "ValueSet",
              url: d2.url ?? `ws:${stem}`,
              compose: {
                include: [...bySystem.entries()].map(([system, cs]) => ({
                  system,
                  concept: cs,
                })),
              },
            };
            onOpenValuesetJson(stem, JSON.stringify(vs, null, 2));
            return;
          }
        }
        setError(`could not load ${name}`);
        return;
      }
      setError(`opening ${name} is not supported yet (S2: CQL + ValueSets)`);
    } catch {
      setError(`could not load ${name}`);
    }
  };

  return (
    <div className="ws-files" data-testid="ws-files">
      <div className="ws-files-actions">
        <button
          type="button"
          className="settings-button"
          data-testid="ws-files-refresh"
          onClick={() => { setNonce((n) => n + 1); onAcknowledgedChanges?.(); }}
          title="re-list workspace files (clears change badges)"
        >
          Refresh
        </button>
      </div>
      {error && <div className="ws-files-error" role="alert">{error}</div>}
      {trees === null && <div className="nav-empty">loading…</div>}
      {trees !== null &&
        GROUPS.map((g) => {
          const files = (trees[g.dir] ?? []).filter(
            (e) => e.kind === "file" && (!g.suffixes || g.suffixes.includes(e.suffix.toLowerCase())),
          );
          if (!files.length) return null;
          return (
            <div key={g.dir} className="ws-files-group" data-testid={`ws-group-${g.dir}`}>
              <div className="ws-files-group-header">{g.label}</div>
              {files.map((f) => {
                const changed = changedPaths.has(`${g.dir}/${f.name}`);
                return (
                  <button
                    key={f.name}
                    type="button"
                    className={`ws-file-row${changed ? " has-change" : ""}`}
                    data-testid={`ws-file-${g.dir}-${f.name}`}
                    onClick={() => void openFile(g.dir, f.name)}
                    title={changed ? `${f.name} — changed on disk` : f.name}
                  >
                    <span className="ws-file-name">{f.name}</span>
                    {changed && <span className="ws-file-dot" aria-label="changed on disk" />}
                  </button>
                );
              })}
            </div>
          );
        })}
    </div>
  );
}
