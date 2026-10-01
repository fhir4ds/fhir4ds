/**
 * WORKBENCH_REORG phase 3 — editor tab model.
 *
 * One tab = one workspace resource open in the editor column. Tabs are
 * pure data ({kind, resourceId}); the host switch lives in
 * components/tabs/hosts.tsx. TabId doubles as the nav item id shape
 * (`kind:resourceId`) so nav clicks open tabs without translation.
 */

export type TabKind =
  | "library"
  | "measure"
  | "valueset"
  | "parameter"
  | "test"
  | "expected"
  | "view";

export type TabId = `${TabKind}:${string}`;

export interface EditorTab {
  id: TabId;
  kind: TabKind;
  resourceId: string;
}

export function tabId(kind: TabKind, resourceId: string): TabId {
  return `${kind}:${resourceId}`;
}

export function parseTabId(id: string): { kind: TabKind; resourceId: string } {
  const sep = id.indexOf(":");
  return { kind: id.slice(0, sep) as TabKind, resourceId: id.slice(sep + 1) };
}

/** Open (or focus) a tab in `tabs`; returns the next array. */
export function openTab(tabs: EditorTab[], tab: EditorTab): EditorTab[] {
  return tabs.some((t) => t.id === tab.id) ? tabs : [...tabs, tab];
}

/** Close a tab; returns the next array. */
export function closeTab(tabs: EditorTab[], id: TabId): EditorTab[] {
  return tabs.filter((t) => t.id !== id);
}

/** Tab to activate after closing `id`: right neighbor, else left, else none. */
export function neighborTabId(
  tabs: EditorTab[],
  id: TabId,
): TabId | null {
  const i = tabs.findIndex((t) => t.id === id);
  if (i === -1) return null;
  return (tabs[i + 1] ?? tabs[i - 1])?.id ?? null;
}
