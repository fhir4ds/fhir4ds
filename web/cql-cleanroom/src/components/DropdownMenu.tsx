import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Header dropdown menu (U4): button + popover list; closes on
 * outside-click or Escape. Items may be plain actions or labelled
 * group headers for submenu-ish sections.
 */
export function DropdownMenu({
  label,
  testId,
  children,
}: {
  label: string;
  testId: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div className="dropdown-menu" ref={ref}>
      <button
        data-testid={testId}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {label} ▾
      </button>
      {open && (
        <div
          className="dropdown-list"
          data-testid={`${testId}-menu`}
          onClick={(e) => {
            // BUBBLE phase: the item's own onClick has already run by
            // the time this fires (capture-phase close unmounted the
            // button mid-click and swallowed the action). Settings rows
            // (selects) and submenu triggers are not actions — they
            // keep the menu open.
            const target = e.target as HTMLElement;
            if (target.closest(".dropdown-sub-trigger")) return;
            if (target.closest(".dropdown-item")) {
              setOpen(false);
            }
          }}
        >
          {children}
        </div>
      )}
    </div>
  );
}

/**
 * #64: one-level flyout inside a DropdownMenu (File > Open / Save /
 * Examples). Opens on hover AND click; the mouseleave close is delayed
 * so diagonal travel trigger → flyout doesn't flicker it shut. Slides
 * out to the LEFT (the File menu hugs the header's right edge... or the
 * title's, both leave no room on the right).
 */
export function DropdownSubmenu({
  label,
  testId,
  children,
}: {
  label: string;
  testId: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const closeTimer = useRef<number | null>(null);
  useEffect(
    () => () => {
      if (closeTimer.current !== null) clearTimeout(closeTimer.current);
    },
    [],
  );
  const enter = () => {
    if (closeTimer.current !== null) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
    setOpen(true);
  };
  const leave = () => {
    closeTimer.current = window.setTimeout(() => {
      closeTimer.current = null;
      setOpen(false);
    }, 220);
  };
  return (
    <div className="dropdown-sub" onMouseEnter={enter} onMouseLeave={leave}>
      <button
        className="dropdown-item dropdown-sub-trigger"
        data-testid={testId}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {label}
        <span className="dropdown-sub-caret" aria-hidden>
          ▸
        </span>
      </button>
      {open && (
        <div className="dropdown-sublist" data-testid={`${testId}-menu`}>
          {children}
        </div>
      )}
    </div>
  );
}
