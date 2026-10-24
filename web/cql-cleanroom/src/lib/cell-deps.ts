/**
 * Client-side cell dependency analysis (c-wasm-bolton S3).
 *
 * Port of the server's refs-of discipline (cells.py refs_of +
 * dependency_closure) to a lexical client form: identifiers defined by
 * OTHER cells that appear in this cell's body are deps. The server walks
 * the parsed AST; the client approximates lexically (word-boundary
 * occurrences of known cell names, excluding self/params/quoted strings).
 * Parity is pinned by test: client closure == server closure on fixture
 * + adversarial libraries (shadowing defines, out-of-order cells).
 */

import { splitCells } from "./cells";

/** Keyword/context names never treated as cell refs (kept: reference surface from the bolton port). */
export const NON_REFS = new Set([
  "Patient", "Practitioner", "unfiltered", "Population", "context", "library",
  "using", "include", "version", "define", "function", "valueset", "codesystem",
  "code", "concept", "parameter", "default", "true", "false", "null",
]);

export interface CellGraph {
  /** cell name -> direct refs to other cell names present in the library */
  refs: Record<string, string[]>;
  /** cell order as authored */
  order: string[];
  /** header text (library/using/context declarations) */
  header: string;
}

export function buildCellGraph(text: string): CellGraph {
  const { header, cells } = splitCells(text);
  // Duplicate names: LAST definition wins (server refs_of dict semantics —
  // pinned by the adversarial parity fixture's shadowing defines).
  const names = new Set(cells.map((c) => c.name));
  const refs: Record<string, string[]> = {};
  for (const cell of cells) {
    // Strip comments before scanning; collect QUOTED spans separately —
    // string contents are not references, but QUOTED IDENTIFIERS are
    // (define "Initial Population": ... "InAgeRange" — the quoted form is
    // how CQL references defines whose names need quoting; S10 binder
    // repro: stripping them silently dropped every quoted-name dep).
    const noComments = cell.text
      .replace(/\/\/[^\n]*/g, " ")
      .replace(/\/\*[\s\S]*?\*\//g, " ");
    // CQL: single quotes = string literals (never refs); DOUBLE quotes =
    // quoted identifiers (valid refs). Only double-quoted spans feed the
    // identifier set; both are removed from the bare-scan text.
    const doubleQuoted: string[] = [];
    const stripped = noComments
      .replace(/'[^']*'/g, " ")
      .replace(/"[^"]*"/g, (m) => {
        doubleQuoted.push(m);
        return " ";
      });
    const quotedContents = new Set(
      doubleQuoted.map((s) => s.slice(1, -1)),
    );
    const found: string[] = [];
    for (const other of names) {
      if (other === cell.name) continue;
      const re = new RegExp(`\\b${escapeRe(other)}\\b`);
      // Bare identifier reference in code ...
      if (re.test(stripped)) {
        found.push(other);
        continue;
      }
      // ... or the exact quoted form ("Other Name" with the quotes).
      if (quotedContents.has(other)) {
        found.push(other);
      }
    }
    refs[cell.name] = found; // last-wins on duplicate names
  }
  return { refs, order: cells.map((c) => c.name), header };
}

/** Post-order DFS closure — mirrors server dependency_closure exactly. */
export function dependencyClosure(
  target: string,
  refs: Record<string, string[]>,
  available: Set<string>,
): string[] {
  const result: string[] = [];
  const visiting = new Set<string>();
  const done = new Set<string>();
  const visit = (name: string) => {
    if (done.has(name) || visiting.has(name)) return;
    visiting.add(name);
    for (const ref of refs[name] ?? []) {
      if (available.has(ref) && ref !== name) visit(ref);
    }
    visiting.delete(name);
    done.add(name);
    result.push(name);
  };
  visit(target);
  return result;
}

/** RunMode expansion (identical semantics both engines — FDD Q2):
 *  cell = [target]; cell_deps = closure; to_here = authored cells up to
 *  and including target (authored order). */
export function expandRunMode(
  mode: "cell" | "cell_deps" | "to_here" | "run_all",
  target: string,
  graph: CellGraph,
): string[] {
  const available = new Set(graph.order);
  if (mode === "cell") return [target];
  if (mode === "cell_deps") return dependencyClosure(target, graph.refs, available);
  const idx = graph.order.indexOf(target);
  return idx === -1 ? [target] : graph.order.slice(0, idx + 1);
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
