export interface CqlSymbolEntry {
  name: string;
  /** 1-based declaration line (outline jumps + gutter links). */
  line: number;
}

export interface CqlSymbols {
  defines: CqlSymbolEntry[];
  functions: CqlSymbolEntry[];
  parameters: CqlSymbolEntry[];
  valuesets: CqlSymbolEntry[];
  codesystems: CqlSymbolEntry[];
  codeDecls: CqlSymbolEntry[];
  /** `include X version '…' called Y` — alias defaults to X's last segment. */
  includes: Array<{ name: string; alias: string; line: number }>;
}

const QUOTED = String.raw`"(?<q>[^"]+)"`;
const BARE = String.raw`(?<b>[A-Za-z][\w]*)`;
const NAME = String.raw`(?:${QUOTED}|${BARE})`;
const MODS = String.raw`(?:fluent\s+)?(?:private\s+|public\s+)?`;

const DECL_PATTERNS: Array<{ kind: keyof Omit<CqlSymbols, "includes">; re: RegExp }> = [
  { kind: "functions", re: new RegExp(`^\\s*define\\s+${MODS}function\\s+${NAME}`) },
  { kind: "defines", re: new RegExp(`^\\s*define\\s+${MODS}${NAME}`) },
  { kind: "parameters", re: new RegExp(`^\\s*parameter\\s+${NAME}`) },
  { kind: "valuesets", re: new RegExp(`^\\s*valueset\\s+${NAME}`) },
  { kind: "codesystems", re: new RegExp(`^\\s*codesystem\\s+${NAME}`) },
  { kind: "codeDecls", re: new RegExp(`^\\s*code\\s+${NAME}`) },
];
const INCLUDE_QUOTED = new RegExp(`^\\s*include\\s+${QUOTED}`);
const INCLUDE_BARE = new RegExp(`^\\s*include\\s+([A-Za-z][\\w.]*)`);
const CALLED = /\bcalled\s+([A-Za-z][\w]*)/;

/**
 * Local, keystroke-fast symbol extraction for editor intelligence
 * (completions, hover, outline). Regex-scanned per line — deliberately
 * NOT the engine parser (parse_cql is an async round-trip; editing
 * needs sub-millisecond symbol tables and tolerates half-written
 * syntax).
 */
export function extractCqlSymbols(text: string): CqlSymbols {
  const out: CqlSymbols = {
    defines: [],
    functions: [],
    parameters: [],
    valuesets: [],
    codesystems: [],
    codeDecls: [],
    includes: [],
  };
  const seen = new Set<string>();
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNo = i + 1;
    let matched = false;
    for (const p of DECL_PATTERNS) {
      const m = p.re.exec(line);
      if (!m) continue;
      const name = m.groups?.q ?? m.groups?.b ?? "";
      const key = `${p.kind}:${name}`;
      if (!seen.has(key)) {
        seen.add(key);
        out[p.kind].push({ name, line: lineNo });
      }
      matched = true;
      break;
    }
    if (matched) continue;
    const inc = INCLUDE_QUOTED.exec(line) ?? INCLUDE_BARE.exec(line);
    if (inc) {
      const name = inc[1];
      const alias = CALLED.exec(line)?.[1] ?? (name.split(".").pop() ?? name);
      out.includes.push({ name, alias, line: lineNo });
    }
  }
  return out;
}

/** Count body references to a symbol name, excluding its own
 *  declaration line (outline usage badges). */
export function countReferences(text: string, name: string, declLine: number): number {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(`(?<!\\w)${escaped}(?!\\w)`, "g");
  let count = 0;
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    if (i + 1 === declLine) continue;
    count += (lines[i].match(re) ?? []).length;
  }
  return count;
}
