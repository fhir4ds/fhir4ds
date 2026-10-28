/**
 * cellify (c-cleanroom-redo S7): synthesize `// # %% [name: X]` markers
 * before each TOP-LEVEL define in a markerless CQL library.
 *
 * Doctrine (directive 3): the markers ARE the metadata — indistinguishable
 * from hand-authored ones; no proprietary format; files stay plain CQL.
 *
 * Parse guard (directive edge cases): candidate defines are detected with
 * the SAME DEFINE regex cells.ts uses for cell identity, plus a line-state
 * scanner so `define` lines inside block comments (or after line comments,
 * or inside string literals) are NOT split. Files that already carry any
 * cell markers are returned untouched (cellify never duplicates metadata).
 */
import { splitCells } from "./cells";

const DEFINE_LINE =
  /^\s*define\s+(function\s+)?("?)([A-Za-z0-9_ ]+)\2\s*[(:]/i;
// Name with spaces (quoted "My Func") is valid CQL but NOT marker-safe —
// those get a BARE marker (cell identity still derives from the define
// text via splitCells' DEFINE rule).

/**
 * Advance the (blockComment) state across one line, respecting // line
 * comments and quoted strings so comment/string contents cannot toggle
 * block state. CQL string literals and quoted identifiers terminate on
 * their own line ('' / "" are the escapes) — a `define` keyword inside
 * either can never appear at the START of its line anyway, so only the
 * block-comment carry matters across lines.
 */
interface LineState {
  block: boolean;
  /** quote char of an UNTERMINATED string carrying to the next line */
  openQuote: "'" | '"' | null;
}

function scanLine(line: string, st: LineState): LineState {
  let { block, openQuote } = st;
  let i = 0;
  while (i < line.length) {
    if (block) {
      const end = line.indexOf("*/", i);
      if (end === -1) return { block: true, openQuote: null };
      i = end + 2;
      block = false;
      continue;
    }
    if (openQuote) {
      const q = openQuote;
      while (i < line.length) {
        if (line[i] === q) {
          if (line[i + 1] === q) {
            i += 2;
            continue;
          }
          openQuote = null;
          i += 1;
          break;
        }
        i += 1;
      }
      continue;
    }
    const c = line[i];
    if (c === "/" && line[i + 1] === "/") return { block: false, openQuote: null };
    if (c === "/" && line[i + 1] === "*") {
      block = true;
      i += 2;
      continue;
    }
    if (c === "'" || c === '"') {
      openQuote = c;
      i += 1;
      continue;
    }
    i += 1;
  }
  return { block, openQuote };
}

/**
 * Return the cellified text, or null when there is nothing to do
 * (already marked, or no top-level defines). Named markers carry the
 * define name; quoted defines whose name is not marker-safe fall back
 * to a bare `// # %%` marker (identity still derives from the define).
 */
export function cellify(text: string): string | null {
  if (splitCells(text).cells.length > 0) return null;
  const lines = text.split("\n");
  const out: string[] = [];
  let st: LineState = { block: false, openQuote: null };
  let inserted = 0;
  for (const line of lines) {
    if (!st.block && !st.openQuote) {
      const m = DEFINE_LINE.exec(line);
      if (m) {
        const name = m[3].trim();
        const markerSafe = /^[A-Za-z0-9_]+$/.test(name);
        out.push(markerSafe ? `// # %% [name: ${name}]` : "// # %%");
        inserted += 1;
      }
    }
    out.push(line);
    st = scanLine(line, st);
  }
  return inserted > 0 ? out.join("\n") : null;
}

/** True when the text has >=1 top-level define (cellify candidate). */
export function hasSplittableDefines(text: string): boolean {
  return cellify(text) !== null;
}
