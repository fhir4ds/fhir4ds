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

export function libraryItems(
  libraries: WorkspaceLibrary[],
  entrypointId: string | null,
  errorsById?: Record<string, boolean>,
): NavItem[] {
  return libraries.map((lib, i) => ({
    id: `library:${lib.id}`,
    kind: "library" as const,
    label: lib.name,
    sublabel: lib.text.split("\n")[0]?.trim() || undefined,
    entry: lib.id === entrypointId,
    error: errorsById?.[lib.id] === true,
    meta: { index: i, libraryId: lib.id },
  }));
}

export function measureItems(
  measures: WorkspaceMeasureEntry[],
  activeMeasureId: string | null,
): NavItem[] {
  return measures.map((m) => {
    const name =
      typeof m.resource?.name === "string"
        ? (m.resource.name as string)
        : "(unauthored)";
    return {
      id: `measure:${m.id}`,
      kind: "measure" as const,
      label: name,
      sublabel: m.resource ? `entry: ${m.mainLibraryId}` : "no populations yet",
      entry: m.id === activeMeasureId,
      meta: { measureId: m.id, mainLibraryId: m.mainLibraryId },
    };
  });
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
    label: String(v.name ?? v.id ?? v.url ?? `valueset ${i + 1}`),
    sublabel: String(v.url ?? ""),
    meta: { source: "workspace" as const, index: i, url: v.url },
  }));
  const ds = datasetValuesets
    .filter((v) => !(typeof v?.url === "string" && wsUrls.has(v.url)))
    .map((v, i) => ({
      id: `valueset:ds:${String(v.url ?? i)}`,
      kind: "valueset" as const,
      label: String(v.name ?? v.id ?? v.url ?? `dataset valueset ${i + 1}`),
      sublabel: String(v.url ?? ""),
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

/** One item per authored expected MeasureReport (per patient). */
export function expectedItems(
  reports: Array<Record<string, unknown>>,
): NavItem[] {
  type PopCoding = { code?: string };
  type Population = { code?: { coding?: PopCoding[] }; count?: number };
  type Group = { population?: Population[] };
  return reports.map((r, i) => {
    const ref = String(
      (r.subject as { reference?: string } | undefined)?.reference ?? `#${i}`,
    );
    const populations: Population[] =
      ((r.group as Group[] | undefined)?.flatMap((g) => g.population ?? []) ??
        []);
    const positive = populations.filter((p) => p.count === 1).length;
    return {
      id: `expected:${ref}`,
      kind: "expected" as const,
      label: ref.replace(/^Patient\//, ""),
      sublabel: `${positive}/${populations.length} populations`,
      meta: { index: i, reference: ref },
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
