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
        <div className="dropdown-list" data-testid={`${testId}-menu`}>
          {children}
        </div>
      )}
    </div>
  );
}
