export interface ParamBinding {
  name: string;
  value: string;
}

export function detectParams(cqlText: string): string[] {
  const names: string[] = [];
  for (const m of cqlText.matchAll(/parameter\s+"([^"]+)"\s+([A-Za-z][A-Za-z0-9_<>\s]*)/g)) {
    if (!names.includes(m[1])) names.push(m[1]);
  }
  return names;
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
