/**
 * useWorkspaceFiles (c-cleanroom-redo S6): connected-mode disk file trees
 * from the sandboxed /api/fs/list — one fetch per known group. Replaces
 * the WorkspaceFilesPanel's private loader so the TYPE DRAWERS can merge
 * disk items (libraries → Libraries, valuesets → ValueSets, data/views
 * → Views drawer grouping) while the Workspace rail section dissolves.
 *
 * Watcher badges stay in App (wsChanged) — they relocate ONTO the merged
 * rows (amber highlight treatment from ebdb9e21 carries over).
 */
import { useCallback, useEffect, useState } from "react";

export interface FsEntry {
  name: string;
  kind: "dir" | "file";
  suffix: string;
}

export const WS_GROUPS: { dir: string; suffixes?: string[] }[] = [
  { dir: "cql", suffixes: [".cql"] },
  { dir: "valuesets", suffixes: [".json"] },
  { dir: "data", suffixes: [".ndjson", ".json"] },
  { dir: "views", suffixes: [".json"] },
];

export interface WorkspaceFilesState {
  /** dir -> file entries (kind === "file", suffix-matched) */
  files: Record<string, FsEntry[]>;
  /** Bump to re-list (Refresh); also clears change badges upstream. */
  reload: () => void;
  loading: boolean;
}

export function useWorkspaceFiles(connected: boolean): WorkspaceFilesState {
  const [trees, setTrees] = useState<Record<string, FsEntry[]> | null>(null);
  const [nonce, setNonce] = useState(0);

  const load = useCallback(() => {
    if (!connected) return;
    Promise.all(
      WS_GROUPS.map((g) =>
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
      for (const r of results) {
        const g = WS_GROUPS.find((x) => x.dir === r.dir);
        out[r.dir] = r.entries.filter(
          (e) =>
            e.kind === "file" &&
            (!g?.suffixes || g.suffixes.includes(e.suffix.toLowerCase())),
        );
      }
      setTrees(out);
    });
  }, [connected]);

  useEffect(load, [load, nonce]);

  return {
    files: trees ?? {},
    reload: () => setNonce((n) => n + 1),
    loading: trees === null,
  };
}
