export interface ParamBinding {
  name: string;
  /** Declared CQL type ("Interval<DateTime>", "String", …) — absent when
   *  the declaration is malformed. */
  type?: string;
  value: string;
}

const PARAM_DECL_RE =
  /parameter\s+"([^"]+)"\s+(Interval\s*<\s*[A-Za-z]+\s*>|[A-Za-z][A-Za-z0-9_]*)/g;

export function detectParams(cqlText: string): ParamBinding[] {
  const out: ParamBinding[] = [];
  const seen = new Set<string>();
  for (const m of cqlText.matchAll(PARAM_DECL_RE)) {
    if (!seen.has(m[1])) {
      seen.add(m[1]);
      out.push({ name: m[1], type: m[2].replace(/\s+/g, ""), value: "" });
    }
  }
  return out;
}

export function isIntervalParam(p: ParamBinding): boolean {
  return /^Interval</i.test(p.type ?? "");
}

/** Parse a raw panel value into the engine's parameter shape.
 *  Interval<DateTime>-style params accept "start..end" or ISO "start/end"
 *  syntax; everything else passes as the plain string. */
export function coerceParam(raw: string): unknown {
  const v = raw.trim();
  // Interval forms: "A .. B" or "A / B"
  const iv = v.match(/^(.+?)\s*\.\.\s*(.+)$/) ?? v.match(/^(.+?)\s*\/\s*(.+)$/);
  if (iv) {
    return { start: iv[1].trim(), end: iv[2].trim() };
  }
  return v;
}

/** Extract the yyyy-mm-dd halves of an interval value for date inputs —
 *  null when the value isn't a two-sided interval with dates. */
export function splitInterval(raw: string): { start: string; end: string } | null {
  const v = coerceParam(raw);
  if (typeof v !== "object" || v === null) return null;
  const { start, end } = v as { start: string; end: string };
  const date = (s: string) => /(\d{4}-\d{2}-\d{2})/.exec(s)?.[1] ?? null;
  const a = date(start);
  const b = date(end);
  return a && b ? { start: a, end: b } : null;
}

/** Build the canonical interval string from the date pickers. DateTime
 *  intervals get conventional boundary times so the END day is inclusive;
 *  Date intervals stay date-only. Empty halves mean unbound. */
export function joinInterval(type: string | undefined, start: string, end: string): string {
  if (!start || !end) return "";
  const t = (type ?? "").replace(/\s+/g, "");
  if (/^Interval<\s*Date\s*>$/i.test(t)) return `${start}..${end}`;
  return `${start}T00:00:00.0..${end}T23:59:59.999`;
}

/** FHIR Parameters view of the bound values (interop artifact for real
 *  engines): intervals become valuePeriod, everything else valueString. */
export function toParametersResource(
  values: Record<string, string>,
): Record<string, unknown> {
  const parameter: Array<Record<string, unknown>> = [];
  for (const [name, raw] of Object.entries(values)) {
    if (typeof raw !== "string" || raw.trim() === "") continue;
    const v = coerceParam(raw);
    if (typeof v === "object" && v !== null) {
      const iv = v as { start: string; end: string };
      parameter.push({ name, valuePeriod: { start: iv.start, end: iv.end } });
    } else {
      parameter.push({ name, valueString: v });
    }
  }
  return { resourceType: "Parameters", parameter };
}
