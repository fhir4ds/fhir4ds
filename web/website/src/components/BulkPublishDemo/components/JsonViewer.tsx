import { useMemo } from "react";

interface JsonViewerProps {
  /** The JSON value to display. */
  value: unknown;
  /** Maximum height before scrolling. Default 400px. */
  maxHeight?: string;
}

/**
 * Pretty-printed JSON viewer with basic syntax coloring. Not as fancy as a
 * Monaco editor but ~30 lines, no dependencies, and fine for resource inspection.
 *
 * Coloring is done via token spans and CSS classes (see styles.css). Strings,
 * numbers, booleans, null, and keys each get their own color.
 */
export function JsonViewer({ value, maxHeight = "400px" }: JsonViewerProps) {
  const html = useMemo(() => renderJson(value), [value]);
  return (
    <pre
      className="json-viewer"
      style={{ maxHeight }}
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderJson(value: unknown, indent = 0): string {
  const pad = "  ".repeat(indent);
  const padInner = "  ".repeat(indent + 1);

  if (value === null) return `<span class="tok-null">null</span>`;
  if (typeof value === "boolean") {
    return `<span class="tok-bool">${value}</span>`;
  }
  if (typeof value === "number") {
    return `<span class="tok-num">${value}</span>`;
  }
  if (typeof value === "string") {
    return `<span class="tok-str">"${escapeHtml(value)}"</span>`;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return "[]";
    const items = value.map((v) => padInner + renderJson(v, indent + 1)).join(",\n");
    return `[\n${items}\n${pad}]`;
  }
  if (typeof value === "object" && value !== undefined) {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return "{}";
    const items = entries
      .map(
        ([k, v]) =>
          `${padInner}<span class="tok-key">"${escapeHtml(k)}"</span>: ${renderJson(v, indent + 1)}`,
      )
      .join(",\n");
    return `{\n${items}\n${pad}}`;
  }
  return escapeHtml(String(value));
}
