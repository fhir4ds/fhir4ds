/**
 * S32: Open/Save workspace pickers (connected) + Recent workspaces.
 *
 * Workspaces are DIRECTORIES on the dev server. The browser picker is a
 * server directory browser (`GET /api/fs/browse`, roots allowlisted
 * server-side); switching posts the absolute path to
 * `/api/workspace/switch`. Recents persist in localStorage (3 pinned
 * examples + the last 10 opened).
 */

export interface BrowseEntry {
  name: string;
  path: string;
  kind: "dir";
  workspace: boolean;
}

export interface BrowseResult {
  entries: BrowseEntry[];
  path?: string;
  parent?: string | null;
  workspace?: boolean;
  roots?: string[];
}

export async function browseFolders(path?: string): Promise<BrowseResult> {
  const url = path
    ? `/api/fs/browse?path=${encodeURIComponent(path)}`
    : "/api/fs/browse";
  const res = await fetch(url);
  const body = (await res.json()) as { data?: BrowseResult } & BrowseResult;
  const d = (body?.data ?? body) as BrowseResult;
  if (!d) throw new Error("browse failed");
  return d;
}

export async function switchWorkspaceByPath(
  path: string,
): Promise<{ ok: boolean; message: string }> {
  const res = await fetch("/api/workspace/switch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  const body = (await res.json()) as {
    data?: { ok?: boolean; diagnostics?: { message?: string }[] };
  } & { ok?: boolean; diagnostics?: { message?: string }[] };
  const d = body?.data ?? body;
  if (d?.ok === false) {
    return {
      ok: false,
      message: d?.diagnostics?.[0]?.message ?? "switch failed",
    };
  }
  return { ok: true, message: "switched" };
}

export async function savePackageToFolder(
  measure: string,
  folder: string,
  filename?: string,
): Promise<{ ok: boolean; message: string; path?: string }> {
  const res = await fetch("/api/package/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ measure, folder, filename }),
  });
  const body = (await res.json()) as {
    data?: { ok?: boolean; path?: string; diagnostics?: { message?: string }[] };
  } & { ok?: boolean; path?: string; diagnostics?: { message?: string }[] };
  const d = body?.data ?? body;
  if (d?.ok === false) {
    return {
      ok: false,
      message: d?.diagnostics?.[0]?.message ?? "save failed",
    };
  }
  return { ok: true, message: "saved", path: d?.path };
}

// ---- Recents (localStorage) -------------------------------------------------

const RECENTS_KEY = "fhir4ds.cleanroom.recentWorkspaces";
const RECENTS_MAX = 10;

export interface RecentWorkspace {
  name: string;
  path: string;
}

export const PINNED_EXAMPLES: RecentWorkspace[] = [
  { name: "demo-workspace", path: "examples/demo-workspace" },
  { name: "cms69-workspace", path: "examples/cms69-workspace" },
  { name: "cms125-workspace", path: "examples/cms125-workspace" },
];

export function loadRecents(): RecentWorkspace[] {
  try {
    const raw = localStorage.getItem(RECENTS_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw) as RecentWorkspace[];
    if (!Array.isArray(arr)) return [];
    // Sanitize legacy entries: dedupe by NAME (old builds could record
    // the same workspace twice — once by registry name, once by path).
    const seen = new Set<string>();
    return arr.filter((r) => {
      if (!r || typeof r.name !== "string" || typeof r.path !== "string") {
        return false;
      }
      if (seen.has(r.name)) return false;
      seen.add(r.name);
      return true;
    });
  } catch {
    return [];
  }
}

export function pushRecent(entry: RecentWorkspace): RecentWorkspace[] {
  // Dedupe by NAME and by path: a workspace switched by registry name
  // stores path = name, while the picker stores an absolute path — the
  // same workspace must never appear twice.
  const next = [
    entry,
    ...loadRecents().filter(
      (r) => r.path !== entry.path && r.name !== entry.name,
    ),
  ].slice(0, RECENTS_MAX);
  try {
    localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
  } catch {
    /* storage full/blocked — recents are best-effort */
  }
  return next;
}
