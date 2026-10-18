/**
 * Client-side cell parsing/marshalling for the v2 notebook layer.
 *
 * Mirrors fhir4ds/devserver/cells.py split semantics: `// # %% [name: X]`
 * markers; header = everything before the first marker.
 */

export interface SplitCell {
  name: string;
  text: string;
  order: number;
}

export interface SplitResult {
  header: string;
  cells: SplitCell[];
}

// S10: marker labels may carry quoted define names WITH SPACES
// ('[name: Initial Population]').
const MARKER = /^\s*\/\/\s*#\s*%%(\s*\[name:\s*([A-Za-z0-9_][A-Za-z0-9_ ]*?)\s*\])?\s*$/;
// c-wasm-bolton S3: quoted define identifiers (define "Combined":) name
// the cell Combined — mirrors server-side statement identity. (Gap found
// by the cell-parity harness; pre-bolton dev-server cells.ts misses it.)
// S8: quoted names may contain spaces (define "My Func":) — capture them;
// identity = the QUOTED name when present, else the bare identifier.
const DEFINE = /^\s*define\s+(function\s+)?("?)([A-Za-z0-9_ ]+?)\2\s*[(:]/;

export function splitCells(text: string): SplitResult {
  const lines = text.split("\n");
  const headerLines: string[] = [];
  const cells: SplitCell[] = [];
  let label: string | null = null;
  let body: string[] = [];
  let inCell = false;
  let order = 0;

  const finish = () => {
    const cellText = body.join("\n").trim();
    if (!cellText) return;
    const m = DEFINE.exec(cellText);
    const name = m ? m[3] : label ?? `cell-${order}`;
    cells.push({ name, text: cellText, order });
    order += 1;
  };

  for (const line of lines) {
    const m = MARKER.exec(line);
    if (m) {
      if (inCell) finish();
      label = m[2] ?? null;
      body = [];
      inCell = true;
      continue;
    }
    if (inCell) body.push(line);
    else headerLines.push(line);
  }
  if (inCell) finish();
  return { header: headerLines.join("\n"), cells };
}

/**
 * S19: single composition authority — both App.runCells (execution) and
 * CellEditor.runCell (run-context capture for evidence) build the exact
 * same composed-closure library text through THIS helper. Never duplicate
 * the recipe.
 */
export function composeCellClosure(
  header: string,
  cells: Array<{ name: string; text: string }>,
  names: string[],
): string {
  return [
    header,
    ...names.map((n) => cells.find((c) => c.name === n)?.text ?? ""),
  ].join("\n\n");
}

/** Split the editor buffer into [header, cellText, gap]* render chunks. */
export interface EditorChunk {
  type: "header" | "cell";
  text: string;
  name?: string;
  order?: number;
}

export function chunkEditor(text: string): EditorChunk[] {
  const lines = text.split("\n");
  const chunks: EditorChunk[] = [];
  let current: string[] = [];
  let currentType: "header" | "cell" = "header";
  let currentName: string | undefined;

  let order = 0;
  const flush = () => {
    const t = current.join("\n");
    if (t.trim()) {
      chunks.push(
        currentType === "cell"
          ? { type: "cell", text: t, name: currentName, order }
          : { type: "header", text: t },
      );
      if (currentType === "cell") order += 1;
    }
  };

  for (const line of lines) {
    if (MARKER.test(line)) {
      flush();
      current = [line];
      currentType = "cell";
      const m = MARKER.exec(line);
      currentName = m?.[2] ?? undefined;
    } else {
      current.push(line);
    }
  }
  flush();
  // Bare `// # %%` markers carry no label; derive the chunk name from the
  // define inside the cell body (mirrors splitCells + server-side identity).
  // The chunk text INCLUDES the marker line, so search past it.
  const defineAnywhere = /^\s*define\s+(function\s+)?("?)([A-Za-z0-9_ ]+?)\2\s*[(:]/m;
  for (const chunk of chunks) {
    if (chunk.type === "cell" && !chunk.name) {
      const m = defineAnywhere.exec(chunk.text);
      if (m?.[3]) chunk.name = m[3];
    }
  }
  return chunks;
}
