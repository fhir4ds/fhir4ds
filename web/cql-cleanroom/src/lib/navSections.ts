import type {
  WorkspaceLibrary,
  WorkspaceMeasureEntry,
  WorkspaceViewDefEntry,
} from "../state/workspace";

/**
 * WORKBENCH_REORG phase 2 — the 7 nav drawers' shared item model. Pure
 * adapters from workspace collections to render-ready items so filtering
 * and labeling stay unit-testable and the drawer stays dumb.
 */

export type NavKind =
  | "measure"
  | "library"
  | "valueset"
  | "parameter"
  | "test"
  | "expected"
  | "view";

export type NavSectionId =
  | "measures"
  | "libraries"
  | "valuesets"
  | "parameters"
  | "tests"
  | "expected"
  | "views";

export interface NavItem {
  /** Stable identity: `${kind}:${resourceId}`. */
  id: string;
  kind: NavKind;
  label: string;
  sublabel?: string;
  /** Small chip on the row's right edge (e.g. resource version). */
  pill?: string;
  entry?: boolean;
  error?: boolean;
  /** S6: item sourced from the server workspace disk (/api/fs). */
  onDisk?: boolean;
  /** S6: a session item that ALSO exists on disk (chip copy differs). */
  diskShadow?: boolean;
  /** S6: watcher-marked changed on disk (amber row treatment). */
  changed?: boolean;
  /** Row payload for handlers (index, resource, source, …). */
  meta?: Record<string, unknown>;
}

export function filterItems(items: NavItem[], q: string): NavItem[] {
  const needle = q.trim().toLowerCase();
  if (!needle) return items;
  return items.filter(
    (it) =>
      it.label.toLowerCase().includes(needle) ||
      it.id.toLowerCase().includes(needle) ||
      (it.sublabel ?? "").toLowerCase().includes(needle),
  );
}

/** Pull `library <name> version '<ver>'` out of the CQL header — the
 *  text is authoritative, so the nav labels default from it. */
export function parseLibraryHeader(
  text: string,
): { name?: string; version?: string } {
  const m = /\blibrary\s+([A-Za-z][A-Za-z0-9_]*)\s*(?:version\s+'([^']*)')?/.exec(
    text,
  );
  if (!m) return {};
  return { name: m[1], version: m[2] };
}

export function libraryItems(
  libraries: WorkspaceLibrary[],
  entrypointId: string | null,
  errorsById?: Record<string, boolean>,
): NavItem[] {
  return libraries.map((lib, i) => {
    const header = parseLibraryHeader(lib.text);
    return {
      id: `library:${lib.id}`,
      kind: "library" as const,
      label: header.name ?? lib.name,
      pill: header.version,
      entry: lib.id === entrypointId,
      error: errorsById?.[lib.id] === true,
      meta: { index: i, libraryId: lib.id },
    };
  });
}

export function measureItems(
  measures: WorkspaceMeasureEntry[],
  activeMeasureId: string | null,
): NavItem[] {
  return measures.map((m) => {
    const name =
      typeof m.resource?.name === "string"
        ? (m.resource.name as string)
        : undefined;
    const version =
      typeof m.resource?.version === "string"
        ? (m.resource.version as string)
        : undefined;
    return {
      id: `measure:${m.id}`,
      kind: "measure" as const,
      label: name ?? m.id,
      pill: version,
      entry: m.id === activeMeasureId,
      meta: {
        measureId: m.id,
        mainLibraryId: m.mainLibraryId,
        name,
      },
    };
  });
}

/** Human label for a ValueSet resource: `name`, then `title`, then `id`,
 *  then the url's last path segment (fresh workspace valuesets are born
 *  with only a generated url). Undefined when the resource is unusable. */
export function valuesetLabel(
  v: Record<string, unknown> | null | undefined,
): string | undefined {
  if (!v) return undefined;
  const str = (k: string) =>
    typeof v[k] === "string" && (v[k] as string).trim() !== ""
      ? (v[k] as string)
      : undefined;
  const url = str("url");
  const seg = url?.includes("/")
    ? url.slice(url.lastIndexOf("/") + 1)
    : undefined;
  return str("name") ?? str("title") ?? str("id") ?? seg ?? url;
}

/** Workspace ValueSets override dataset ones by url (same merge rule as
 *  evalDataset). Sources are labeled so deletes only touch workspace copies. */
export function valuesetItems(
  workspaceValuesets: Array<Record<string, unknown>>,
  datasetValuesets: Array<Record<string, unknown>>,
): NavItem[] {
  const wsUrls = new Set(
    workspaceValuesets
      .map((v) => (typeof v?.url === "string" ? v.url : null))
      .filter(Boolean) as string[],
  );
  const ws = workspaceValuesets.map((v, i) => ({
    id: `valueset:ws:${String(v.url ?? i)}`,
    kind: "valueset" as const,
    label: valuesetLabel(v) ?? `valueset ${i + 1}`,
    pill:
      typeof v.version === "string" && v.version.trim() !== ""
        ? v.version
        : undefined,
    meta: {
      source: "workspace" as const,
      index: i,
      url: v.url,
      name: typeof v.name === "string" ? v.name : undefined,
    },
  }));
  const ds = datasetValuesets
    .filter((v) => !(typeof v?.url === "string" && wsUrls.has(v.url)))
    .map((v, i) => ({
      id: `valueset:ds:${String(v.url ?? i)}`,
      kind: "valueset" as const,
      label: valuesetLabel(v) ?? `dataset valueset ${i + 1}`,
      pill:
        typeof v.version === "string" && v.version.trim() !== ""
          ? v.version
          : undefined,
      meta: { source: "dataset" as const, url: v.url },
    }));
  return [...ws, ...ds];
}

export function parameterItems(
  params: Array<{ name: string; value: string }>,
): NavItem[] {
  return params.map((p) => ({
    id: `parameter:${p.name}`,
    kind: "parameter" as const,
    label: p.name,
    sublabel: p.value.trim() === "" ? "unbound" : p.value,
    meta: { name: p.name },
  }));
}

/** One EXPECTED item per measure — the expectations editor is
 *  per-measure (its grid gains rows as patients are added), so the nav
 *  lists the resource even before any expectations are authored. */
export function expectedItems(
  measures: WorkspaceMeasureEntry[],
  expectedReports: Record<string, Array<Record<string, unknown>>>,
): NavItem[] {
  return measures.map((m) => {
    const reports = expectedReports[m.id] ?? [];
    const nPatients = reports.filter(
      (r) =>
        typeof (r.subject as { reference?: string } | undefined)
          ?.reference === "string",
    ).length;
    const name =
      typeof m.resource?.name === "string"
        ? (m.resource.name as string)
        : m.id;
    return {
      id: `expected:${m.id}`,
      kind: "expected" as const,
      label: name,
      sublabel: `${nPatients} patients`,
      meta: { measureId: m.id },
    };
  });
}

export function viewItems(viewDefs: WorkspaceViewDefEntry[]): NavItem[] {
  return viewDefs.map((v, i) => ({
    id: `view:${v.id}`,
    kind: "view" as const,
    label: v.name || v.id,
    sublabel: String(
      (v.resource as { resource?: string } | undefined)?.resource ?? "",
    ),
    meta: { index: i, viewDefId: v.id },
  }));
}

/**
 * S6 disk-provenance merge — /api/fs/list file entries flow into the TYPE
 * drawers. NavItem gains `onDisk?: boolean` (renders an "on disk" chip)
 * and `changed?: boolean` (watcher badge relocates onto these rows —
 * amber highlight treatment from ebdb9e21 carries over).
 */
export interface DiskFileRef {
  name: string;
  changed?: boolean;
}

/** Merge rule (S6 directive): one row per resource; when a resource
 *  exists BOTH on disk and in-session, disk WINS on provenance display
 *  (the row keeps its in-session id/handlers but shows the on-disk chip
 *  and carries disk open/changed semantics). */
export function mergeDiskLibraries(
  items: NavItem[],
  disk: DiskFileRef[],
  /** S17 Muse: parsed header names per file (from /api/workspace) — rows
   *  display the CANONICAL library name; clicks resolve directly. */
  headerNames?: Record<string, string>,
): NavItem[] {
  const diskByStem = new Map(disk.map((d) => [d.name.replace(/\.cql$/i, ""), d]));
  const headerFor = (stem: string) => headerNames?.[stem] ?? stem;
  const merged = items.map((it) => {
    const d = diskByStem.get(it.label) ?? diskByStem.get(it.meta?.libraryId as string ?? "");
    return d
      ? { ...it, onDisk: true, diskShadow: true, changed: d.changed }
      : it;
  });
  const sessionLabels = new Set(merged.map((it) => it.label));
  const extras: NavItem[] = [];
  for (const [stem, d] of diskByStem) {
    const canonical = headerFor(stem);
    if (!sessionLabels.has(stem) && !sessionLabels.has(canonical)) {
      extras.push({
        id: `library:disk:${stem}`,
        kind: "library",
        label: canonical,
        onDisk: true,
        changed: d.changed,
        sublabel: stem === canonical ? undefined : d.name,
        meta: { source: "disk", name: d.name, libName: canonical },
      });
    }
  }
  return [...merged, ...extras];
}

export function mergeDiskValuesets(
  items: NavItem[],
  disk: DiskFileRef[],
  /** S22a: file stem -> FHIR resource id (labels disk rows by identity). */
  idByStem?: Record<string, string>,
): NavItem[] {
  const diskByName = new Map(disk.map((d) => [d.name.replace(/\.json$/i, ""), d]));
  const merged = items.map((it) => {
    const d = diskByName.get(it.label);
    return d ? { ...it, onDisk: true, diskShadow: true, changed: d.changed } : it;
  });
  const sessionLabels = new Set(merged.map((it) => it.label));
  const extras: NavItem[] = [];
  for (const [stem, d] of diskByName) {
    if (!sessionLabels.has(stem)) {
      extras.push({
        id: `valueset:disk:${stem}`,
        kind: "valueset",
        label: idByStem?.[stem] ?? stem,
        onDisk: true,
        changed: d.changed,
        meta: { source: "disk", name: d.name },
      });
    }
  }
  return [...merged, ...extras];
}

export function mergeDiskViews(
  items: NavItem[],
  diskViews: DiskFileRef[],
  diskData: DiskFileRef[],
): NavItem[] {
  // Views drawer carries BOTH view files and data files (current
  // grouping logic: data files keep the data-hint/restart banner
  // behavior via meta.source === "disk-data").
  const viewByName = new Map(
    diskViews.map((d) => [d.name.replace(/\.json$/i, ""), d]),
  );
  const merged = items.map((it) => {
    const d = viewByName.get(it.label);
    return d ? { ...it, onDisk: true, diskShadow: true, changed: d.changed } : it;
  });
  const sessionLabels = new Set(merged.map((it) => it.label));
  const extras: NavItem[] = [];
  const dataByName = new Map(
    diskData.map((d) => [d.name.replace(/\.ndjson$/i, "").replace(/\.json$/i, ""), d]),
  );
  const seenExtras = new Set<string>();
  for (const group of [
    { map: viewByName, isData: false },
    { map: dataByName, isData: true },
  ]) {
    for (const [stem, d] of group.map) {
      const dedupeKey = `${group.isData ? "data" : "view"}:${stem}`;
      if (seenExtras.has(dedupeKey)) continue;
      const asView = viewByName.has(stem);
      if (!group.isData && sessionLabels.has(stem)) continue;
      if (group.isData && asView) continue; // same-stem view wins the row
      seenExtras.add(dedupeKey);
      extras.push({
        id: `${group.isData ? "disk-data" : "disk-view"}:${stem}`,
        kind: "view",
        label: stem,
        onDisk: true,
        changed: d.changed,
        sublabel: group.isData ? "data" : "",
        meta: { source: group.isData ? "disk-data" : "disk-view", name: d.name },
      });
    }
  }
  return [...merged, ...extras];
}
