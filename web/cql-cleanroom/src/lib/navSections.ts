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
