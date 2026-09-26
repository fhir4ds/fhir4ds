import type { ReactNode } from "react";
import { DrawerSection, DrawerRow } from "./nav/DrawerSection";
import type { NavItem, NavSectionId } from "../lib/navSections";

/**
 * REORG phase 6d — maps-style nav. L1: an icon strip, one button per
 * section (testid `nav-toggle-{id}`; clicking the active section
 * collapses the rail). L2: a slide-out panel hosting exactly ONE
 * DrawerSection at a time (App defaults it to Tests so `dataset-loaded`
 * stays the visible boot signal). The drawer header caret closes the
 * panel (`nav-close-{id}`). Legacy e2e aliases survive: `library-tabs`
 * (hidden span), `library-tab-N`, `library-tab-add`, `rail-collapse`,
 * `nav-rail`, and the `.rail-badge.*` classes. The rail's T button opens
 * the terminology drawer in col1 (`drawer-terminology-toggle`), not a
 * section panel.
 */

export interface NavRailSectionModel {
  title: string;
  items: NavItem[];
  count: number;
  filter: string;
  showFilter?: boolean;
}

const SECTION_ORDER: NavSectionId[] = [
  "measures",
  "libraries",
  "valuesets",
  "parameters",
  "tests",
  "expected",
  "views",
];

const SECTION_GLYPHS: Record<NavSectionId, string> = {
  measures: "M",
  libraries: "L",
  valuesets: "V",
  parameters: "P",
  tests: "▦",
  expected: "E",
  views: "◇",
};

function rowTestId(item: NavItem, index: number): string {
  if (item.kind === "library") {
    return `library-tab-${item.meta?.index ?? index}`;
  }
  return `nav-item-${item.kind}-${String(item.id).replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

export function NavRail({
  sections,
  navPanel,
  onNavPanelChange,
  onFilterSection,
  onItemSelect,
  onItemDoubleClick,
  onItemContextMenu,
  renaming,
  renameValue,
  onRenameChange,
  onRenameCommit,
  onRenameCancel,
  onAddLibrary,
  onAddView,
  onAddExpected,
  onTerminologyOpen,
  terminologyOpen = false,
  testsSlot,
}: {
  sections: Record<NavSectionId, NavRailSectionModel>;
  /** The single open section (null = collapsed rail). */
  navPanel: NavSectionId | null;
  onNavPanelChange: (id: NavSectionId | null) => void;
  onFilterSection: (id: NavSectionId, v: string) => void;
  onItemSelect: (item: NavItem) => void;
  onItemDoubleClick: (item: NavItem) => void;
  onItemContextMenu: (item: NavItem, x: number, y: number) => void;
  renaming: string | null;
  renameValue: string;
  onRenameChange: (v: string) => void;
  onRenameCommit: () => void;
  onRenameCancel: () => void;
  onAddLibrary: () => void;
  onAddView: () => void;
  onAddExpected: () => void;
  /** Opens the terminology drawer in col1 (below the editor). */
  onTerminologyOpen: () => void;
  terminologyOpen?: boolean;
  testsSlot?: ReactNode;
}) {
  const panelId = navPanel;
  const sec = panelId ? sections[panelId] : null;
  const actions =
    panelId === "libraries" ? (
      <button
        className="nav-add-btn"
        data-testid="library-tab-add"
        title="add library"
        onClick={onAddLibrary}
      >
        +
      </button>
    ) : panelId === "views" ? (
      <button
        className="nav-add-btn"
        data-testid="nav-add-views"
        title="new ViewDefinition"
        onClick={onAddView}
      >
        +
      </button>
    ) : panelId === "expected" ? (
      <button
        className="nav-add-btn"
        data-testid="nav-add-expected"
        title="author expected results"
        onClick={onAddExpected}
      >
        +
      </button>
    ) : undefined;
  return (
    <nav
      className={`nav-rail ${panelId ? "" : "collapsed"}`}
      data-testid="nav-rail"
      aria-label="workspace navigation"
    >
      {/* Legacy alias: e2e greps `^=library-tab-` — the wrapper keeps the
          per-item testid, this hidden span keeps the container testid. */}
      <span hidden data-testid="library-tabs" />
      <div className="rail-strip">
        <div className="rail-header">
          <button
            className="rail-collapse-btn"
            data-testid="rail-collapse"
            title={panelId ? "collapse rail" : "expand rail"}
            onClick={() => onNavPanelChange(panelId ? null : "tests")}
          >
            {panelId ? "«" : "»"}
          </button>
        </div>
        {SECTION_ORDER.map((id) => (
          <button
            key={id}
            className={`rail-item ${panelId === id ? "active" : ""}`}
            data-testid={`nav-toggle-${id}`}
            title={sections[id].title}
            onClick={() => onNavPanelChange(panelId === id ? null : id)}
          >
            <span className="rail-glyph">{SECTION_GLYPHS[id]}</span>
            <span className="rail-name">{sections[id].title}</span>
          </button>
        ))}
        <div className="rail-sep" />
        <button
          className={`rail-item ${terminologyOpen ? "active" : ""}`}
          data-testid="drawer-terminology-toggle"
          title="Terminology (ValueSets)"
          onClick={onTerminologyOpen}
        >
          <span className="rail-glyph">T</span>
          <span className="rail-name">Terminology</span>
        </button>
      </div>
      {panelId && sec && (
        <div className="nav-panel">
          <DrawerSection
            key={panelId}
            id={panelId}
            title={sec.title}
            count={sec.count}
            expanded
            onToggle={() => onNavPanelChange(null)}
            filter={sec.filter}
            onFilter={(v) => onFilterSection(panelId, v)}
            showFilter={sec.showFilter !== false}
            actions={actions}
          >
            {sec.items.length === 0 && panelId !== "tests" && (
              <div className="nav-empty">none</div>
            )}
            {sec.items.map((item, i) => (
              <DrawerRow
                key={item.id}
                item={item}
                active={item.entry}
                testId={rowTestId(item, i)}
                onClick={() => onItemSelect(item)}
                onDoubleClick={() => onItemDoubleClick(item)}
                onContextMenu={(e) => onItemContextMenu(item, e.clientX, e.clientY)}
                renaming={renaming === item.id}
                renameValue={renameValue}
                onRenameChange={onRenameChange}
                onRenameCommit={onRenameCommit}
                onRenameCancel={onRenameCancel}
              />
            ))}
            {panelId === "tests" && testsSlot}
          </DrawerSection>
        </div>
      )}
    </nav>
  );
}
