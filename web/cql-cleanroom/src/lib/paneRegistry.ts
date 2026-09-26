/**
 * WORKBENCH_REORG phase 5: the second column renders these panes in
 * order. Drag-reorder is future UI over the same data — order persists
 * in prefs.layout.paneOrder. Panes stay mounted when toggled off.
 */
export type PaneId = "measure-report" | "view";

export interface PaneDef {
  id: PaneId;
  title: string;
  defaultOpen: boolean;
}

export const PANE_REGISTRY: PaneDef[] = [
  { id: "measure-report", title: "Measure Report", defaultOpen: true },
  { id: "view", title: "View Definition", defaultOpen: true },
];

export const DEFAULT_PANE_ORDER: PaneId[] = PANE_REGISTRY.map((p) => p.id);

export function normalizePaneOrder(order: unknown): PaneId[] {
  if (!Array.isArray(order)) return DEFAULT_PANE_ORDER;
  const ids = order.filter(
    (id): id is PaneId =>
      typeof id === "string" && PANE_REGISTRY.some((p) => p.id === id),
  );
  for (const p of PANE_REGISTRY) {
    if (!ids.includes(p.id)) ids.push(p.id);
  }
  return ids;
}
