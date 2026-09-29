import { extractCqlSymbols } from "./cqlSymbols";

/**
 * Visual editor step 5 — expression builder model for HEDIS-style
 * define shapes. The builder round-trips ONE define at a time:
 *
 *   library text ──parseDefine──▶ BuilderExpr ──serializeDefine──▶ body
 *        ▲                                                    │
 *        └──────────────spliceDefine (Apply)◀─────────────────┘
 *
 * Recognized shape: a single retrieve (optionally valueset-qualified)
 * with an `and`-joined where of flat predicates. Any conjunct outside
 * that grammar becomes a "custom" atom — preserved VERBATIM so the
 * round-trip is lossless for real-world measure logic (function calls,
 * intervals, or/nesting all degrade to custom atoms, never dropped).
 * A define whose whole body doesn't match stays kind:"custom" and is
 * edited as text.
 */

export interface BuilderLiteral {
  kind: "string" | "number" | "boolean" | "datetime";
  value: string;
}

export type BuilderAtom =
  | { type: "compare"; path: string; op: string; literal: BuilderLiteral }
  | { type: "valueset"; path: string; valueset: string }
  | { type: "custom"; text: string };

export interface BuilderRetrieve {
  resourceType: string;
  alias: string;
  valueset?: string;
}

export interface BuilderExpr {
  name: string;
  kind: "exists" | "list" | "custom";
  retrieve: BuilderRetrieve | null;
  where: BuilderAtom[];
  /** Verbatim body when kind === "custom". */
  raw: string;
}

export const COMPARE_OPS = ["=", "!=", "<=", ">=", "<", ">", "~"] as const;

const BODY_RETRIEVE =
  /^\s*\[([A-Za-z][\w]*)\s*(?::\s*"([^"]+)")?\s*\]\s*(?:([A-Za-z][\w]*)\s*)?(?:where\s+([\s\S]+))?\s*$/;

/** `exists([Type: "VS"] A where W)` | `exists([Type] A)` |
 *  `[Type: "VS"] A where W` | `[Type] A`. */
function parseBody(body: string): Omit<BuilderExpr, "name"> | null {
  // No whitespace collapsing: custom atoms keep the author's text
  // (multiline wheres survive the round-trip verbatim).
  const trimmed = body.trim();
  const exists = /^exists\s*\(\s*([\s\S]+)\s*\)\s*$/.exec(trimmed);
  const inner = exists ? exists[1] : trimmed;
  const m = BODY_RETRIEVE.exec(inner);
  if (!m) return null;
  const whereText = m[4]?.trim();
  return {
    kind: exists ? "exists" : "list",
    retrieve: {
      resourceType: m[1],
      alias: m[3] ?? "",
      valueset: m[2] || undefined,
    },
    where: whereText ? parseConjunction(whereText) : [],
    raw: body.trim(),
  };
}

/** Split a where on top-level `and`, parsing each conjunct. If any
 *  fragment has unbalanced parens (nested or/grouping), the whole
 *  where degrades to ONE custom atom — safer than mis-splitting. */
export function parseConjunction(whereText: string): BuilderAtom[] {
  const parts = whereText.split(/\s+and\s+/);
  if (parts.some((p) => !balanced(p))) {
    return [{ type: "custom", text: whereText }];
  }
  return parts.map(parseAtom);
}

function balanced(s: string): boolean {
  let depth = 0;
  for (const ch of s) {
    if (ch === "(") depth++;
    else if (ch === ")") depth--;
    if (depth < 0) return false;
  }
  return depth === 0;
}

const COMPARE_RE =
  /^([A-Za-z][\w]*(?:\.[\w]+)*)\s*(~=|!=|<=|>=|=|<|>|~)\s*([\s\S]+)$/;
const VALUESET_RE = /^([A-Za-z][\w]*(?:\.[\w]+)*)\s+in\s+"([^"]+)"$/;

export function parseAtom(fragmentRaw: string): BuilderAtom {
  const fragment = fragmentRaw.trim();
  const vs = VALUESET_RE.exec(fragment);
  if (vs) return { type: "valueset", path: vs[1], valueset: vs[2] };
  const cmp = COMPARE_RE.exec(fragment);
  if (cmp) {
    const literal = classifyLiteral(cmp[3].trim());
    if (literal) {
      return { type: "compare", path: cmp[1], op: cmp[2], literal };
    }
  }
  return { type: "custom", text: fragment };
}

function classifyLiteral(raw: string): BuilderLiteral | null {
  const str = /^'([\s\S]*)'$/.exec(raw);
  if (str) return { kind: "string", value: str[1].replace(/''/g, "'") };
  if (/^-?\d+(\.\d+)?$/.test(raw)) return { kind: "number", value: raw };
  if (raw === "true" || raw === "false") {
    return { kind: "boolean", value: raw };
  }
  if (/^@[\dT:\-.]+(Z|[+-]\d{2}:\d{2})?$/.test(raw)) {
    return { kind: "datetime", value: raw };
  }
  return null;
}

function renderLiteral(l: BuilderLiteral): string {
  switch (l.kind) {
    case "string":
      return "'" + l.value.replace(/'/g, "''") + "'";
    case "boolean":
      return l.value;
    default:
      return l.value;
  }
}

export function serializeAtom(a: BuilderAtom): string {
  switch (a.type) {
    case "compare":
      return `${a.path} ${a.op} ${renderLiteral(a.literal)}`;
    case "valueset":
      return `${a.path} in "${a.valueset}"`;
    case "custom":
      return a.text.trim();
  }
}

export function serializeBody(e: BuilderExpr): string {
  if (e.kind === "custom") return e.raw.trim();
  const r = e.retrieve ?? { resourceType: "Patient", alias: "", valueset: undefined };
  const vs = r.valueset ? `: "${r.valueset}"` : "";
  const al = r.alias ? ` ${r.alias}` : "";
  const head = `[${r.resourceType}${vs}]${al}`;
  const where = e.where.length
    ? ` where ${e.where.map(serializeAtom).join(" and ")}`
    : "";
  return e.kind === "exists" ? `exists(${head}${where})` : `${head}${where}`;
}

export function serializeDefine(e: BuilderExpr): string {
  return `define "${e.name}":\n  ${serializeBody(e)}`;
}

/** Parse ONE define out of the library text by name. kind:"custom"
 *  when the body is outside the builder grammar (raw kept verbatim). */
export function parseDefine(libText: string, name: string): BuilderExpr | null {
  const decl = extractCqlSymbols(libText).defines.find((d) => d.name === name);
  if (!decl) return null;
  const body = defineBody(libText, decl.line);
  const parsed = parseBody(body);
  if (!parsed) return { name, kind: "custom", retrieve: null, where: [], raw: body };
  return { name, ...parsed, raw: body };
}

/** The define's body: lines after the declaration until the next
 *  top-level statement (or EOF), trimmed. */
export function defineBody(libText: string, declLine: number): string {
  const lines = libText.split("\n");
  const body: string[] = [];
  for (let i = declLine; i < lines.length; i++) {
    if (TOP_LEVEL_RE.test(lines[i])) break;
    body.push(lines[i]);
  }
  return body.join("\n").trim();
}

const TOP_LEVEL_RE =
  /^\s*(library\b|using\b|include\b|parameter\b|valueset\b|codesystem\b|code\b|concept\b|context\b|define\b)/;

/** Replace ONE define's statement block with new statement text
 *  (name row + indented body). Statement must already exist. */
export function spliceDefine(
  libText: string,
  name: string,
  statement: string,
): string {
  const decl = extractCqlSymbols(libText).defines.find((d) => d.name === name);
  if (!decl) return libText;
  const lines = libText.split("\n");
  let end = declLineEnd(lines, decl.line);
  return [...lines.slice(0, decl.line - 1), ...statement.split("\n"), ...lines.slice(end)].join("\n");
}

function declLineEnd(lines: string[], declLine: number): number {
  for (let i = declLine; i < lines.length; i++) {
    if (i + 1 > declLine && TOP_LEVEL_RE.test(lines[i])) return i;
  }
  return lines.length;
}

/** Append a brand-new define statement at the end of the library. */
export function appendDefine(libText: string, statement: string): string {
  const base = libText.replace(/\s+$/, "");
  return `${base}\n\n${statement}\n`;
}
