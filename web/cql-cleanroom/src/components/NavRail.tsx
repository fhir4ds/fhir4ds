import { useRef, type ReactNode } from "react";
import {
  BookOpen,
  Database,
  Ruler,
  SlidersHorizontal,
  Table,
  Tags,
  Target,
  type LucideIcon,
} from "lucide-react";
import { DrawerSection, DrawerRow } from "./nav/DrawerSection";
import { DropdownMenu } from "./DropdownMenu";
import type { NavItem, NavSectionId } from "../lib/navSections";

/**
 * REORG phase 6d — maps-style nav. L1: an icon strip, one button per
 * section (testid `nav-toggle-{id}`; clicking the active section
 * collapses the rail). L2: a slide-out panel hosting exactly ONE
 * DrawerSection at a time (App defaults it to Tests so the dataset
 * tree stays the visible boot signal). The drawer header caret closes the
 * panel (`nav-close-{id}`). Legacy e2e aliases survive: `library-tabs`
 * (hidden span), `library-tab-N`, `library-tab-add`, `rail-collapse`,
 * `nav-rail`, and the `.rail-badge.*` classes. The rail's T button
 * (`drawer-terminology-toggle`) toggles Terminology as an EDITOR tab
 * (REORG 6e), not a section panel.
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

const SECTION_ICONS: Record<NavSectionId, LucideIcon> = {
  measures: Ruler,
  libraries: BookOpen,
  valuesets: Tags,
  parameters: SlidersHorizontal,
  tests: Database,
  expected: Target,
  views: Table,
};

function rowTestId(item: NavItem, index: number): string {
  if (item.kind === "library") {
    return `library-tab-${item.meta?.index ?? index}`;
  }
  return `nav-item-${item.kind}-${String(item.id).replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

/** REORG 6h #64: the section header's ▾ imports items from files (the
 *  + button still creates from scratch). File-interop only — tests may
 *  import a single resource OR a Bundle; everything else is typed. */
const IMPORT_ITEMS: Partial<
  Record<NavSectionId, Array<{ item: string; label: string }>>
> = {
  measures: [{ item: "measure-json", label: "Import Measure .json…" }],
  libraries: [
    { item: "library-cql", label: "Import .cql…" },
    { item: "library-json", label: "Import FHIR Library .json…" },
  ],
  valuesets: [{ item: "valueset-json", label: "Import ValueSet .json…" }],
  parameters: [{ item: "parameters-json", label: "Import Parameters .json…" }],
  views: [{ item: "view-json", label: "Import ViewDefinition .json…" }],
  tests: [
    { item: "resource-json", label: "Import resource .json…" },
    { item: "bundle-json", label: "Import Bundle .json…" },
  ],
  expected: [
    { item: "expected-json", label: "Import MeasureReport .json…" },
  ],
};

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
  onAddMeasures,
  onAddTests,
  onAddView,
  onAddExpected,
  onAddValuesets,
  onImportItem,
  panelWidth,
  detailWidth,
  onPanelWidth,
  onDetailWidth,
  detailSlot,
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
  /** Creates a blank Measure bound to the entrypoint library. */
  onAddMeasures: () => void;
  /** Opens a fresh resource-builder tab (dataset authoring). */
  onAddTests: () => void;
  onAddView: () => void;
  onAddExpected: () => void;
  /** Creates a fresh workspace ValueSet and opens its editor tab. */
  onAddValuesets: () => void;
  /** #64: the ▾ split-button — import one item from a file into the
   *  section (`IMPORT_ITEMS[section]` keys the chosen item). */
  onImportItem: (section: NavSectionId, item: string) => void;
  /** REORG 6h: resizable slide-outs — px widths + drag callbacks. */
  panelWidth: number;
  detailWidth: number;
  onPanelWidth: (w: number) => void;
  onDetailWidth: (w: number) => void;
  /** REORG 6e: focused Tests patient (drives the slide-out overlay). */
  focusedPid?: string | null;
  /** REORG 6e: L3 detail panel, rendered over the section panel. */
  detailSlot?: ReactNode;
  testsSlot?: ReactNode;
}) {
  const panelId = navPanel;
  const sec = panelId ? sections[panelId] : null;
  // REORG 6h: slide-out resize — pointer drag on the edge handles; px
  // deltas map 1:1 onto the width while the grid column (--nav-w) tracks.
  const dragRef = useRef<{
    key: "panel" | "detail";
    startX: number;
    startW: number;
  } | null>(null);
  const resizeDown = (key: "panel" | "detail") => (e: React.PointerEvent) => {
    dragRef.current = {
      key,
      startX: e.clientX,
      startW: key === "panel" ? panelWidth : detailWidth,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const resizeMove = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    const [min, max] = d.key === "panel" ? [168, 480] : [208, 640];
    const w = Math.min(max, Math.max(min, d.startW + (e.clientX - d.startX)));
    (d.key === "panel" ? onPanelWidth : onDetailWidth)(w);
  };
  const resizeUp = (e: React.PointerEvent) => {
    dragRef.current = null;
    e.currentTarget.releasePointerCapture(e.pointerId);
  };
  const resizeHandle = (key: "panel" | "detail") => (
    <div
      className="nav-resize"
      role="separator"
      aria-orientation="vertical"
      aria-label={`Resize ${key} panel`}
      data-testid={`nav-resize-${key}`}
      onPointerDown={resizeDown(key)}
      onPointerMove={resizeMove}
      onPointerUp={resizeUp}
    />
  );
  const plusButton =
    panelId === "measures" ? (
      <button
        className="nav-add-btn"
        data-testid="nav-add-measures"
        title="new Measure"
        onClick={onAddMeasures}
      >
        +
      </button>
    ) : panelId === "tests" ? (
      <button
        className="nav-add-btn"
        data-testid="nav-add-tests"
        title="new resource"
        onClick={onAddTests}
      >
        +
      </button>
    ) : panelId === "libraries" ? (
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
    ) : panelId === "valuesets" ? (
      <button
        className="nav-add-btn"
        data-testid="nav-add-valuesets"
        title="new ValueSet"
        onClick={onAddValuesets}
      >
        +
      </button>
    ) : undefined;
  // Split button: + | ▾ — the ▾ opens the section's file-import items.
  const importItems = panelId ? (IMPORT_ITEMS[panelId] ?? []) : [];
  const actions = (
    <>
      {plusButton}
      {importItems.length > 0 && panelId && (
        <DropdownMenu label="" testId={`nav-import-${panelId}`}>
          {importItems.map((it) => (
            <button
              key={it.item}
              className="dropdown-item"
              data-testid={`nav-import-${panelId}-${it.item}`}
              onClick={() => onImportItem(panelId, it.item)}
            >
              {it.label}
            </button>
          ))}
        </DropdownMenu>
      )}
    </>
  );
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
        {SECTION_ORDER.map((id) => {
          const Icon = SECTION_ICONS[id];
          return (
            <button
              key={id}
              className={`rail-item ${panelId === id ? "active" : ""}`}
              data-testid={`nav-toggle-${id}`}
              title={sections[id].title}
              onClick={() => onNavPanelChange(panelId === id ? null : id)}
            >
              <span className="rail-glyph">
                <Icon size={15} strokeWidth={1.8} aria-hidden />
              </span>
              <span className="rail-name">{sections[id].title}</span>
            </button>
          );
        })}
      </div>
      {panelId && sec && (
        <div className="nav-panel-wrap">
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
          {resizeHandle("panel")}
          {panelId === "tests" && detailSlot && (
            <div className="nav-panel-detail" data-testid="nav-detail">
              {detailSlot}
              {resizeHandle("detail")}
            </div>
          )}
        </div>
      )}
    </nav>
  );
}
