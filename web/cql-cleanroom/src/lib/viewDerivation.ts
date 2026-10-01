/**
 * ViewDefinition derivation from a FHIR Measure (feature §3.5).
 *
 * The Measure is the single authority for population semantics; the
 * View drawer derives one wide-format VD column per population
 * (forEach: group), with per-column fork-on-edit overrides keyed by
 * the normalized population code. Overrides are pure data — the
 * Measure never reads them back.
 */

export interface ViewColumnOverride {
  name?: string;
  path?: string;
}

export type ViewOverrides = Record<string, ViewColumnOverride>;

export interface ViewConfig {
  source: "reports" | "dataset";
  overrides: ViewOverrides;
}

export interface MeasurePopulation {
  code: string;
  define: string;
}

/** hyphenated FHIR code -> sql-name-safe column key. */
export function normalizeCode(code: string): string {
  return code.replace(/-/g, "_");
}

/** Walk Measure.group[].population[] -> {code, define} pairs. */
export function measurePopulations(
  measure: Record<string, unknown> | null,
): MeasurePopulation[] {
  if (!measure) return [];
  const groups = (measure.group as Array<Record<string, unknown>>) ?? [];
  const out: MeasurePopulation[] = [];
  for (const g of groups) {
    for (const pop of (g.population as Array<Record<string, unknown>>) ?? []) {
      const coding =
        (
          (pop.code as Record<string, unknown>)?.coding as
            Array<Record<string, unknown>>
        )?.[0] ?? {};
      const criteria = pop.criteria as Record<string, unknown> | undefined;
      const code = coding.code;
      const define = criteria?.expression;
      if (typeof code === "string" && typeof define === "string" && code && define) {
        out.push({ code, define });
      }
    }
  }
  return out;
}

function sanitizeIdent(s: string): string {
  const cleaned = s.replace(/[^A-Za-z0-9_]/g, "_");
  return /^[0-9]/.test(cleaned) ? `g${cleaned}` : cleaned;
}

export interface DerivedColumn {
  /** normalized population key (override map key). */
  key: string;
  defaultName: string;
  defaultPath: string;
  /** effective name/path (override ?? default). */
  name: string;
  path: string;
  overridden: boolean;
}

/**
 * Derive one column per population. Multi-group measures prefix
 * column names with the group id (g{N}_ fallback) so codes from
 * different groups cannot collide (second-opinion F3).
 */
export function deriveViewColumns(
  measure: Record<string, unknown> | null,
  overrides: ViewOverrides | null | undefined,
): DerivedColumn[] {
  const groups = (measure?.group as Array<Record<string, unknown>>) ?? [];
  const multi = groups.length > 1;
  const out: DerivedColumn[] = [];
  const seen = new Set<string>();
  groups.forEach((g, gi) => {
    const gid = typeof g.id === "string" && g.id ? sanitizeIdent(g.id) : `g${gi + 1}`;
    for (const pop of (g.population as Array<Record<string, unknown>>) ?? []) {
      const coding =
        (
          (pop.code as Record<string, unknown>)?.coding as
            Array<Record<string, unknown>>
        )?.[0] ?? {};
      const code = coding.code;
      if (typeof code !== "string" || !code) continue;
      const key = multi ? `${gid}_${normalizeCode(code)}` : normalizeCode(code);
      if (seen.has(key)) continue;
      seen.add(key);
      const defaultName = key;
      // Wide format: column evaluated against the report ROOT (no
      // forEach group) — one row per patient, population counts read
      // from the matching group (m1081 #9).
      const defaultPath = multi
        ? `group.where(id='${gid}').population.where(code.coding.code='${code}').count.first()`
        : `group.where(population.code.coding.code='${code}').population.count.first()`;
      const ov = overrides?.[key] ?? {};
      const name = ov.name?.trim() || defaultName;
      const path = ov.path?.trim() || defaultPath;
      out.push({
        key,
        defaultName,
        defaultPath,
        name,
        path,
        overridden: Boolean(ov.name?.trim() || ov.path?.trim()),
      });
    }
  });
  return out;
}

/** Override keys that no longer match any derived column (F7). */
export function orphanedOverrides(
  measure: Record<string, unknown> | null,
  overrides: ViewOverrides | null | undefined,
): string[] {
  if (!overrides) return [];
  const live = new Set(deriveViewColumns(measure, overrides).map((c) => c.key));
  return Object.keys(overrides).filter((k) => !live.has(k));
}

export interface DerivedViewColumnSpec {
  name: string;
  path: string;
  type: string;
}

/**
 * Build the wide-format MeasureReport ViewDefinition:
 * ONE ROW PER PATIENT (m1081 #9) — no forEach; patient_id from the
 * report subject; one integer count column per population, read from
 * the matching group via a root-level where() path. Multi-group
 * measures still prefix column names with the group id.
 */
export function buildDerivedView(
  measure: Record<string, unknown> | null,
  overrides: ViewOverrides | null | undefined,
): Record<string, unknown> {
  const columns: DerivedViewColumnSpec[] = [
    { name: "patient_id", path: "%resource.subject.reference", type: "string" },
  ];
  for (const c of deriveViewColumns(measure, overrides)) {
    columns.push({ name: c.name, path: c.path, type: "integer" });
  }
  return {
    resource: "MeasureReport",
    name: "MeasureReportPopulations",
    select: [{ column: columns }],
  };
}
