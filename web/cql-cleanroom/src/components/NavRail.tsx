import type { ReactNode } from "react";
import { DrawerSection, DrawerRow } from "./nav/DrawerSection";
import type { NavItem, NavSectionId } from "../lib/navSections";

/**
 * WORKBENCH_REORG phase 2: the left rail is now SEVEN resource drawers
 * (measures, libraries, valuesets, parameters, tests, expected, views).
 * Legacy e2e aliases survive: `library-tabs` (hidden span),
 * `library-tab-N` (library rows), `library-tab-add`, `rail-dataset`,
 * `rail-terminology`, `nav-rail`, and the `.rail-badge.*` classes.
 */

export interface NavRailSectionModel {
  title: string;
  items: NavItem[];
  count: number;
  expanded: boolean;
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

function rowTestId(item: NavItem, index: number): string {
  if (item.kind === "library") {
    return `library-tab-${item.meta?.index ?? index}`;
  }
  return `nav-item-${item.kind}-${String(item.id).replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

export function NavRail({
  sections,
  onToggleSection,
  onPopSection,
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
  railCollapsed,
  onRailCollapse,
  testsSlot,
}: {
  sections: Record<NavSectionId, NavRailSectionModel>;
  onToggleSection: (id: NavSectionId) => void;
  onPopSection: (id: NavSectionId) => void;
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
  railCollapsed: boolean;
  onRailCollapse: () => void;
  testsSlot?: ReactNode;
}) {
  return (
    <nav
      className={`nav-rail ${railCollapsed ? "collapsed" : ""}`}
      data-testid="nav-rail"
      aria-label="workspace navigation"
    >
      <div className="rail-header">
        <span className="rail-label">Workspace</span>
        <button
          className="rail-collapse-btn"
          data-testid="rail-collapse"
          title={railCollapsed ? "expand rail" : "collapse rail"}
          onClick={onRailCollapse}
        >
          {railCollapsed ? "»" : "«"}
        </button>
      </div>
      {/* Legacy alias: e2e greps `^=library-tab-` — the wrapper keeps the
          per-item testid, this hidden span keeps the container testid. */}
      <span hidden data-testid="library-tabs" />
      {SECTION_ORDER.map((id) => {
        const sec = sections[id];
        const showFilter = sec.showFilter !== false;
        return (
          <DrawerSection
            key={id}
            id={id}
            title={sec.title}
            count={sec.count}
            expanded={sec.expanded && !railCollapsed}
            onToggle={() => onToggleSection(id)}
            filter={sec.filter}
            onFilter={(v) => onFilterSection(id, v)}
            showFilter={showFilter}
            actions={
              id === "libraries" ? (
                <button
                  className="nav-add-btn"
                  data-testid="library-tab-add"
                  title="add library"
                  onClick={onAddLibrary}
                >
                  +
                </button>
              ) : id === "views" ? (
                <button
                  className="nav-add-btn"
                  data-testid="nav-add-views"
                  title="new ViewDefinition"
                  onClick={onAddView}
                >
                  +
                </button>
              ) : id === "expected" ? (
                <button
                  className="nav-add-btn"
                  data-testid="nav-add-expected"
                  title="new expected MeasureReport"
                  onClick={onAddExpected}
                >
                  +
                </button>
              ) : undefined
            }
          >
            {sec.items.length === 0 && id !== "tests" && (
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
            {id === "tests" && testsSlot}
          </DrawerSection>
        );
      })}
      <div className="rail-sep" />
      {/* Quick buttons POP their drawer open (never toggle): with the rail
          collapsed a toggle would silently re-hide an already-open body. */}
      <button
        className={`rail-item ${sections.tests.expanded && !railCollapsed ? "active" : ""}`}
        data-testid="rail-dataset"
        title="Resources (Tests drawer)"
        onClick={() => onPopSection("tests")}
      >
        <span className="rail-glyph">▦</span>
        <span className="rail-name">Resources</span>
      </button>
      <button
        className={`rail-item ${sections.valuesets.expanded && !railCollapsed ? "active" : ""}`}
        data-testid="rail-terminology"
        title="Terminology (ValueSets drawer)"
        onClick={() => onPopSection("valuesets")}
      >
        <span className="rail-glyph">Ⓣ</span>
        <span className="rail-name">Terminology</span>
      </button>
    </nav>
  );
}
