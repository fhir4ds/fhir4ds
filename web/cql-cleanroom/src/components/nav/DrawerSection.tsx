import type { ReactNode } from "react";
import type { NavSectionId } from "../../lib/navSections";

/**
 * WORKBENCH_REORG phase 2 — one collapsible nav drawer: caret, title,
 * count, filter input, item list. Sections stay MOUNTED when collapsed
 * (display:none on the body) so e2e signals inside them (notably
 * dataset-loaded) survive; the Tests drawer defaults expanded so the
 * boot signal is VISIBLE for waitForSelector.
 */

export function DrawerSection({
  id,
  title,
  count,
  expanded,
  onToggle,
  filter,
  onFilter,
  filterPlaceholder = "filter by name or id",
  showFilter = true,
  actions,
  children,
}: {
  id: NavSectionId;
  title: string;
  count: number;
  expanded: boolean;
  onToggle: () => void;
  filter: string;
  onFilter: (v: string) => void;
  filterPlaceholder?: string;
  /** Hosts its own filter UI (e.g. the Tests drawer's DatasetPane). */
  showFilter?: boolean;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      className={`nav-drawer ${expanded ? "open" : ""}`}
      data-testid={`nav-sec-${id}`}
    >
      <button
        className="nav-drawer-head"
        data-testid={`nav-toggle-${id}`}
        aria-expanded={expanded}
        onClick={onToggle}
      >
        <span className="nav-drawer-caret" aria-hidden>
          {expanded ? "▾" : "▸"}
        </span>
        <span className="nav-drawer-title">{title}</span>
        <span className="nav-drawer-count">{count}</span>
      </button>
      <div className="nav-drawer-body" hidden={!expanded}>
        {showFilter && (
          <div className="nav-drawer-toolbar">
            <input
              className="nav-filter"
              data-testid={`nav-filter-${id}`}
              value={filter}
              placeholder={filterPlaceholder}
              onChange={(e) => onFilter(e.target.value)}
            />
            {actions}
          </div>
        )}
        {!showFilter && actions && (
          <div className="nav-drawer-toolbar">{actions}</div>
        )}
        <div className="nav-drawer-list" data-testid={`nav-list-${id}`}>
          {children}
        </div>
      </div>
    </section>
  );
}

/** A single drawer row: click/double-click/context-menu + badges. */
export function DrawerRow({
  item,
  active,
  testId,
  onClick,
  onDoubleClick,
  onContextMenu,
  renaming,
  renameValue,
  onRenameChange,
  onRenameCommit,
  onRenameCancel,
}: {
  item: { id: string; label: string; sublabel?: string; entry?: boolean; error?: boolean };
  active?: boolean;
  testId: string;
  onClick?: () => void;
  onDoubleClick?: () => void;
  onContextMenu?: (e: React.MouseEvent) => void;
  renaming?: boolean;
  renameValue?: string;
  onRenameChange?: (v: string) => void;
  onRenameCommit?: () => void;
  onRenameCancel?: () => void;
}) {
  if (renaming) {
    return (
      <div className="nav-item renaming" data-testid={`${testId}-rename`}>
        <input
          ref={(el) => {
            if (el) {
              el.focus();
              el.select();
            }
          }}
          value={renameValue ?? ""}
          onChange={(e) => onRenameChange?.(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onRenameCommit?.();
            else if (e.key === "Escape") onRenameCancel?.();
          }}
          onBlur={onRenameCommit}
          aria-label="rename"
        />
      </div>
    );
  }
  return (
    <button
      className={`nav-item ${active ? "active" : ""}`}
      data-testid={testId}
      title={item.sublabel ? `${item.label} — ${item.sublabel}` : item.label}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      onContextMenu={(e) => {
        e.preventDefault();
        onContextMenu?.(e);
      }}
    >
      <span className="nav-item-label">{item.label}</span>
      {item.sublabel && <span className="nav-item-sub">{item.sublabel}</span>}
      {item.entry && <span className="rail-badge entry" aria-label="active" />}
      {item.error && <span className="rail-badge err" aria-label="error" />}
    </button>
  );
}
