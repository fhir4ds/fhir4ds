import { useEffect, useRef } from "react";

/**
 * WORKBENCH_REORG phase 2 — right-click menu for nav drawer items.
 * Rendered by the owner (App) as `{x, y, items} | null`; closes on
 * click-away, Esc, scroll, or item selection.
 */

export interface ContextMenuItem {
  label: string;
  onSelect: () => void;
  danger?: boolean;
}

export interface ContextMenuState {
  x: number;
  y: number;
  title?: string;
  items: ContextMenuItem[];
}

export function ResourceContextMenu({
  menu,
  onClose,
}: {
  menu: ContextMenuState | null;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!menu) return;
    const away = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("mousedown", away);
    window.addEventListener("keydown", key);
    window.addEventListener("scroll", onClose, true);
    return () => {
      window.removeEventListener("mousedown", away);
      window.removeEventListener("keydown", key);
      window.removeEventListener("scroll", onClose, true);
    };
  }, [menu, onClose]);

  if (!menu) return null;
  const clampedX = Math.min(menu.x, window.innerWidth - 190);
  const clampedY = Math.min(menu.y, window.innerHeight - menu.items.length * 30 - 12);
  return (
    <div
      ref={ref}
      className="ctx-menu"
      data-testid="nav-context-menu"
      role="menu"
      style={{ left: clampedX, top: clampedY }}
    >
      {menu.title && <div className="ctx-menu-title">{menu.title}</div>}
      {menu.items.map((it) => (
        <button
          key={it.label}
          role="menuitem"
          className={`ctx-menu-item ${it.danger ? "danger" : ""}`}
          onClick={() => {
            it.onSelect();
            onClose();
          }}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}
