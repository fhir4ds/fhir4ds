/**
 * Box projection (ux3): split the library into header + marked boxes with
 * char spans, mirroring server-side split_boxes. Each box becomes its own
 * editor card; spans are the two-way sync contract (splice-on-change).
 */

export interface Box {
  title: string;
  title_source: "label" | "define" | "header" | "block";
  kind: string; // define | valueset | codesystem | parameter | include | header | block
  name?: string | null; // define name when present
  start: number; // char offset in the master buffer
  end: number; // exclusive
}

const MARKER = /^\s*\/\/\s*#\s*%%(\s*\[name:\s*([A-Za-z0-9_]+)\s*\])?\s*$/;
const DEFINE = /^\s*define\s+(function\s+)?([A-Za-z0-9_]+)\s*[(:]/;
const BLOCK_KIND =
  /^\s*(valueset|codesystem|code|concept|parameter|include|context|using|library)\b/;

export function splitBoxes(text: string): Box[] {
  const lines = text.split(/\r?\n/);
  // Walk lines with offsets where each line's terminator (\n, or \r\n)
  // belongs to the PRECEDING line — mirrors python splitlines(keepends=True)
  // semantics used by the server, so box.start points AT the marker text
  // (never at the leading newline) and spans match server spans exactly.
  let offset = 0;
  let headerEnd = text.length;
  const markers: { start: number; end: number; label: string | null }[] = [];
  for (const line of lines) {
    // Advance past the line content plus its terminator (if any).
    let consumed = line.length;
    let term = 0;
    if (text[offset + consumed] === "\r" && text[offset + consumed + 1] === "\n") {
      term = 2;
    } else if (text[offset + consumed] === "\n") {
      term = 1;
    }
    const start = offset;
    const end = offset + consumed + term;
    const m = MARKER.exec(line);
    if (m) {
      if (headerEnd === text.length) headerEnd = start;
      markers.push({ start, end, label: m[2] ?? null });
    }
    offset = end;
  }
  const boxes: Box[] = [];
  if (headerEnd > 0) {
    boxes.push({
      title: "header",
      title_source: "header",
      kind: "header",
      name: null,
      start: 0,
      end: headerEnd,
    });
  }
  markers.forEach((mk, i) => {
    const bEnd = i + 1 < markers.length ? markers[i + 1].start : text.length;
    const body = text.slice(mk.end, bEnd);
    const stripped = body.trim();
    let kind = "block";
    let name: string | null = null;
    const d = DEFINE.exec(stripped);
    if (d) {
      kind = "define";
      name = d[2];
    } else {
      const kb = BLOCK_KIND.exec(stripped);
      if (kb) kind = kb[1].toLowerCase();
    }
    let title: string;
    let source: Box["title_source"];
    if (mk.label != null) {
      title = mk.label;
      source = "label";
    } else if (name != null) {
      title = name;
      source = "define";
    } else if (stripped) {
      title = kind;
      source = "block";
    } else {
      title = "empty";
      source = "block";
    }
    boxes.push({ title, title_source: source, kind, name, start: mk.start, end: bEnd });
  });
  return boxes;
}

/** Splice an edited box back into the master buffer at its span. */
export function spliceBox(
  buffer: string,
  box: Box,
  newBody: string,
  includeMarker: boolean,
): string {
  if (includeMarker) {
    // Replace the whole span (header box: its full text; or a full-box edit).
    return buffer.slice(0, box.start) + newBody + buffer.slice(box.end);
  }
  // Replace only the body region after the marker line. box.start points AT
  // the marker line's first char (see splitBoxes), so the terminator search
  // lands on the marker line's own \n.
  const markerEnd = markerLineEnd(buffer, box);
  return buffer.slice(0, markerEnd) + newBody + buffer.slice(box.end);
}

/** Insert a new cell box at the end of the buffer; returns [newBuffer]. */
export function appendBox(buffer: string): string {
  const skeleton = "\n// # %%\ndefine NewCell: 'TODO'\n";
  return buffer.trimEnd() + skeleton;
}

/** Rename: rewrite the marker label (label-sourced titles). */
export function renameLabel(buffer: string, box: Box, newTitle: string): string {
  const lineEnd = buffer.indexOf("\n", box.start);
  const e = lineEnd === -1 ? buffer.length : lineEnd;
  return buffer.slice(0, box.start) + `// # %% [name: ${newTitle}]` + buffer.slice(e);
}

/** Rename: define refactor (word-boundary replace across the buffer). */
export function renameDefine(buffer: string, oldName: string, newTitle: string): string {
  const re = new RegExp(`\\b${oldName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g");
  return buffer.replace(re, newTitle);
}

// --- Monaco theme (extracted from the retired DevEditor so per-box editors
// share the same token colors: strings straw/orange, red reserved for errors) ---
import type * as MonacoEditor from "monaco-editor";

let themeDefined = false;

export function defineDevTheme(monaco: typeof MonacoEditor): void {
  if (themeDefined) return;
  themeDefined = true;
  monaco.editor.defineTheme("dev-cql", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "string", foreground: "ce9178" },
      { token: "string.sql", foreground: "ce9178" },
      { token: "string.quote", foreground: "ce9178" },
      { token: "string.value", foreground: "d7ba7d" },
      { token: "keyword", foreground: "569cd6" },
      { token: "comment", foreground: "6a9955", fontStyle: "italic" },
    ],
    colors: {},
  });
}

/** Compute the end of the marker line for a box span (offset just past \n). */
export function markerLineEnd(buffer: string, box: Box): number {
  const nl = buffer.indexOf("\n", box.start);
  return nl === -1 ? buffer.length : nl + 1;
}
