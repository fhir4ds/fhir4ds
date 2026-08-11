import { useState } from "react";

interface CollapsibleCalloutProps {
  /** The text on the toggle button when collapsed. */
  prompt: string;
  /** Optional sub-heading shown when expanded. */
  title?: string;
  /** Content revealed when expanded. */
  children: React.ReactNode;
  /** Default expansion state. */
  defaultOpen?: boolean;
}

/**
 * An expandable callout used for "behind the scenes" technical detail that
 * would distract from the main flow if always visible. Audience members who
 * want the depth can click; others can read past.
 */
export function CollapsibleCallout({
  prompt,
  title,
  children,
  defaultOpen = false,
}: CollapsibleCalloutProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`callout ${open ? "callout--open" : ""}`}>
      <button
        className="callout__toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="callout__caret">{open ? "▾" : "▸"}</span>
        {prompt}
      </button>
      {open && (
        <div className="callout__body">
          {title && <div className="callout__title">{title}</div>}
          {children}
        </div>
      )}
    </div>
  );
}
