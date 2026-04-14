/**
 * Client-side narrative generator — TypeScript port of dqm-py NarrativeGenerator.
 *
 * Consumes grouped evidence from audit_and/audit_or struct output.
 * Each evidence item is a logic group with `trace`, `attribute`, `operator`,
 * `threshold`, and `findings` (list of {target, value}).
 */

const OP_DISPLAY: Record<string, string> = {
  "=": "equals",
  ">": "greater than",
  "<": "less than",
  ">=": "at least",
  "<=": "at most",
  "!=": "not equal to",
  "<>": "not equal to",
  exists: "found",
  absent: "not found",
};

const TEMPLATES: Record<string, string> = {
  "initial-population": "Included in Initial Population",
  denominator: "Eligible for measure denominator",
  "denominator-exclusion": "Excluded from denominator",
  "denominator-exception": "Exception applied",
  numerator: "Met numerator criteria",
  "numerator-exclusion": "Excluded from numerator",
};

const FAILURE_TEMPLATES: Record<string, string> = {
  "initial-population": "Not in Initial Population",
  denominator: "Not eligible for denominator",
  "denominator-exclusion": "Not excluded from denominator",
  "denominator-exception": "No exception applied",
  numerator: "Failed numerator",
  "numerator-exclusion": "Not excluded from numerator",
};

export interface EvidenceGroup {
  attribute?: string;
  operator?: string;
  threshold?: string;
  trace?: string[];
  findings?: { target?: string; value?: string }[];
}

export interface AuditCell {
  result: boolean;
  evidence?: EvidenceGroup[];
}

export function isAuditCell(value: unknown): value is AuditCell {
  if (!value || typeof value !== "object") return false;
  const obj = value as Record<string, unknown>;
  return typeof obj.result === "boolean" && (obj.evidence === undefined || Array.isArray(obj.evidence));
}

export function generateNarrative(
  columnName: string,
  evidence: EvidenceGroup[],
  isSatisfied: boolean,
): string[] {
  const populationCode = columnNameToPopulationCode(columnName);
  const templates = isSatisfied ? TEMPLATES : FAILURE_TEMPLATES;
  const header = templates[populationCode] ?? "Evidence";

  if (!evidence || evidence.length === 0) {
    return [`${header}: no supporting evidence.`];
  }

  const fragments = [`${header}:`];
  for (const group of evidence) {
    const frag = formatGroup(group);
    if (frag) fragments.push(frag);
  }
  return fragments;
}

function columnNameToPopulationCode(name: string): string {
  const lower = name.toLowerCase().replace(/\s+/g, "-");
  if (lower.includes("initial")) return "initial-population";
  if (lower.includes("denominator") && lower.includes("exclu")) return "denominator-exclusion";
  if (lower.includes("denominator") && lower.includes("except")) return "denominator-exception";
  if (lower.includes("denominator")) return "denominator";
  if (lower.includes("numerator") && lower.includes("exclu")) return "numerator-exclusion";
  if (lower.includes("numerator")) return "numerator";
  return lower;
}

function formatGroup(group: EvidenceGroup): string | null {
  const attr = group.attribute;
  const op = group.operator ?? "";
  const threshold = group.threshold;
  const trace = (group.trace ?? []).filter(Boolean).map(String);
  const findings = group.findings ?? [];
  const count = findings.length;

  const opDisplay = OP_DISPLAY[op] ?? op;

  let frag: string;
  if (op === "absent") {
    const resourceLabel = attr ?? resourceTypeFromTrace(trace) ?? "resource";
    const valueset = threshold ?? "required criteria";
    frag = `Logic: No ${resourceLabel} found for ${valueset}`;
  } else if (attr && threshold) {
    frag = `Logic: ${attr} ${opDisplay} ${threshold}`;
  } else if (threshold) {
    frag = `Logic: ${opDisplay} ${threshold}`;
  } else if (opDisplay) {
    frag = `Logic: ${opDisplay}`;
  } else {
    return null;
  }

  if (findings.length > 0) {
    const sample = findings[0];
    const rid = sample.target ?? "Resource";
    const val = sample.value;
    let findingStr = val ? `Finding: ${rid} value=${val}` : `Finding: ${rid}`;
    if (count > 1) findingStr += ` (+${count - 1} more)`;
    frag = `${frag} | ${findingStr}`;
  }

  if (trace.length > 0) {
    frag += ` | Trace: ${trace.join(" > ")}`;
  }

  return frag;
}

function resourceTypeFromTrace(trace: string[]): string | null {
  if (trace.length === 0) return null;
  const first = trace[0];
  if (first.includes(": ")) return first.split(": ", 1)[0];
  return first[0] === first[0].toUpperCase() ? first : null;
}
