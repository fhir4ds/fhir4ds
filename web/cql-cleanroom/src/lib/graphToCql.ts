/**
 * C3-U5: visual algorithm editor → CQL emitter (pure, no React, no DOM).
 *
 * The graph model is a small typed node list + edges. `graphToCql`
 * compiles it to a complete CQL library (define-per-output-node).
 * Discipline (FEATURE_CQL_CLEANROOM_C3.md §3.3, S-C3-C/S-C3-D):
 * - ONE-WAY emit: the canvas writes CQL text; it never edits SQL and
 *   never silently mutates the editor (Apply is explicit).
 * - Round-trip guard: emit → parse_cql ok → re-emit is byte-stable
 *   (canonical serialization: sorted node ids, deterministic walks).
 */

export type GraphNodeKind =
  | "Retrieve"
  | "Property"
  | "Exists"
  | "Where"
  | "And"
  | "Or"
  | "Not"
  | "Comparison"
  | "Literal"
  | "DefineOutput";

export interface GraphNodeData {
  /** Retrieve: resource type. Property: path. Where/Comparison: operator.
   *  Literal: value. DefineOutput: define name. */
  label?: string;
  /** Comparison operator (=, !=, <, <=, >, >=, in). */
  operator?: string;
  /** Property path (dot-separated). */
  path?: string;
  /** Literal value (rendered as CQL literal). */
  value?: string;
}

export interface GraphNode {
  id: string;
  kind: GraphNodeKind;
  data: GraphNodeData;
}

export interface GraphEdge {
  source: string;
  target: string;
  /** Optional input slot name for multi-input nodes (e.g. 'left'/'right'). */
  slot?: string;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

const INDENT = "  ";

function cqlStringLiteral(s: string): string {
  return "'" + s.replace(/'/g, "''") + "'";
}

function cqlLiteral(raw: string | undefined): string {
  if (raw === undefined || raw === "") return "null";
  if (raw === "true" || raw === "false") return raw;
  if (/^-?\d+(\.\d+)?$/.test(raw)) return raw;
  return cqlStringLiteral(raw);
}

function operandsOf(
  node: GraphNode,
  byId: Map<string, GraphNode>,
  incoming: Map<string, GraphEdge[]>,
): string[] {
  const edges = (incoming.get(node.id) ?? [])
    .slice()
    .sort((a, b) => (a.slot ?? "").localeCompare(b.slot ?? "") || a.source.localeCompare(b.source));
  const out: string[] = [];
  for (const e of edges) {
    const src = byId.get(e.source);
    if (src) out.push(src.id);
  }
  return out;
}

/**
 * Emit the CQL expression for one node (recursive descent over the DAG).
 * Returns null for malformed graphs (missing operands etc.) — callers
 * surface a typed error, never garbage SQL.
 */
const MAX_EMIT_DEPTH = 100;

const IDENTIFIER_RE = /^[A-Za-z][A-Za-z0-9_.]*$/;
/** Quoted define names may contain spaces, but not quotes (CQL quotedIdentifier). */
const DEFINE_NAME_RE = /^[A-Za-z][A-Za-z0-9_.' ]*$/;

/** REV-C3-002: identifiers interpolated into CQL must be whitelisted. */
function cqlIdentifier(raw: string, what: string): string {
  if (!IDENTIFIER_RE.test(raw)) {
    throw new Error(
      `invalid ${what} ${JSON.stringify(raw)} — must match ^[A-Za-z][A-Za-z0-9_.]*$`,
    );
  }
  return raw;
}

/** REV-C3-003: define names render inside double quotes — no embedded quotes. */
function cqlDefineName(raw: string): string {
  if (!DEFINE_NAME_RE.test(raw)) {
    throw new Error(
      `invalid define name ${JSON.stringify(raw)} — letters, digits, space, . _ ' only`,
    );
  }
  return raw;
}

/** REV-C3-003: quoted define label — delegates to cqlDefineName. */
function cqlDefineLabel(raw: string): string {
  return cqlDefineName(raw);
}

export function emitNodeExpression(
  nodeId: string,
  graph: Graph,
  byId: Map<string, GraphNode>,
  incoming: Map<string, GraphEdge[]>,
  depth: number,
): string | null {
  if (depth > MAX_EMIT_DEPTH) return null; // REV-C3-001: cycle guard
  const node = byId.get(nodeId);
  if (!node) return null;
  const ops = operandsOf(node, byId, incoming);

  const sub = (i: number): string | null =>
    i < ops.length ? emitNodeExpression(ops[i], graph, byId, incoming, depth + 1) : null;

  switch (node.kind) {
    case "Retrieve": {
      const rt = node.data.label ?? node.data.path ?? "Patient";
      return `[${cqlIdentifier(rt, "Retrieve resource type")}]`;
    }
    case "Property": {
      const path = node.data.path ?? node.data.label ?? "";
      if (!path) return null;
      return ops.length
        ? `(${sub(0)} X return X.${path})`
        : path;
    }
    case "Exists": {
      const inner = sub(0);
      return inner === null ? null : `exists ${inner}`;
    }
    case "Where": {
      const inner = sub(0);
      const pred = sub(1);
      if (inner === null || pred === null) return null;
      return `(${inner} X where ${pred})`;
    }
    case "And":
    case "Or": {
      const a = sub(0);
      const b = sub(1);
      if (a === null || b === null) return null;
      const op = node.kind === "And" ? "and" : "or";
      return `(${a} ${op} ${b})`;
    }
    case "Not": {
      const a = sub(0);
      return a === null ? null : `not (${a})`;
    }
    case "Comparison": {
      const a = sub(0);
      const b = sub(1);
      if (a === null || b === null) return null;
      const op = node.data.operator ?? "=";
      return `(${a} ${op} ${b})`;
    }
    case "Literal": {
      return cqlLiteral(node.data.value ?? node.data.label);
    }
    case "DefineOutput": {
      // Handled at the top level (emitDefine); inside an expression it
      // delegates to its single operand.
      const a = sub(0);
      return a === null ? null : a;
    }
    default:
      return null;
  }
}

/**
 * Compile a graph to a full CQL library string.
 * Every DefineOutput node becomes one `define`.
 * Throws Error with a node id on malformed graphs.
 */
export function graphToCql(graph: Graph, libraryName = "Visual"): string {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const incoming = new Map<string, GraphEdge[]>();
  for (const e of graph.edges) {
    const list = incoming.get(e.target) ?? [];
    list.push(e);
    incoming.set(e.target, list);
  }

  const outputs = graph.nodes
    .filter((n) => n.kind === "DefineOutput")
    .sort((a, b) => a.id.localeCompare(b.id));

  if (!outputs.length) {
    throw new Error("graph has no DefineOutput node — nothing to emit");
  }

  const lines: string[] = [
    `library ${libraryName} version '1.0.0'`,
    "using FHIR version '4.0.1'",
    "include FHIRHelpers version '4.0.1' called FHIRHelpers",
    "",
  ];

  for (const out of outputs) {
    const expr = emitNodeExpression(out.id, graph, byId, incoming, 0);
    if (expr === null) {
      throw new Error(`node ${out.id}: malformed subgraph (missing operand)`);
    }
    const name = out.data.label ?? out.id;
    lines.push(`define "${cqlDefineLabel(name)}":`);
    lines.push(`${INDENT}${expr}`);
    lines.push("");
  }
  return lines.join("\n");
}
