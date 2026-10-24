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

/**
 * S26a (item 5): BOTH layout spellings are listed per group — the
 * legacy dirs (cql/, valuesets/, data/, views/) AND the canonical
 * FHIR-type convention (Library/, ValueSet/, ViewDefinition/, plus
 * Patient/ & friends for data). Mirrors devserver config.py's
 * CONVENTION_DIRS + TYPE_CONVENTION_DIRS merge (both searched,
 * duplicates impossible across distinct dir names).
 */
export const WS_GROUPS: { dirs: string[]; suffixes?: string[] }[] = [
  { dirs: ["cql", "Library"], suffixes: [".cql"] },
  { dirs: ["valuesets", "ValueSet"], suffixes: [".json"] },
  { dirs: ["data", "Patient", "Encounter", "Observation", "Condition", "Procedure"], suffixes: [".ndjson", ".json"] },
  { dirs: ["views", "ViewDefinition"], suffixes: [".json"] },
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
      // S26a: one fetch per DIR (each group may carry several layout
      // spellings; missing dirs resolve to empty entry lists).
      WS_GROUPS.flatMap((g) =>
        g.dirs.map((dir) =>
          fetch(`/api/fs/list?path=${encodeURIComponent(dir)}`)
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
                  return { dir, entries: [] as FsEntry[] };
                }
                return { dir, entries: d?.entries ?? [] };
              },
            )
            .catch(() => ({ dir, entries: [] as FsEntry[] })),
        ),
      ),
    ).then((results) => {
      const groupOf = (dir: string) =>
        WS_GROUPS.find((x) => x.dirs.includes(dir));
      const out: Record<string, FsEntry[]> = {};
      for (const r of results) {
        const g = groupOf(r.dir);
        if (!g) continue;
        const matched = r.entries.filter(
          (e) =>
            e.kind === "file" &&
            (!g.suffixes || g.suffixes.includes(e.suffix.toLowerCase())),
        );
        // Keyed by GROUP's primary dir (legacy spelling) so existing
        // consumers (diskRefs("cql") etc.) keep working.
        const key = g.dirs[0];
        out[key] = [...(out[key] ?? []), ...matched];
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
