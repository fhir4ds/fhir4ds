/**
 * PASS2 G2: ValueSet → engine cache bridge (browser worker side).
 *
 * The WASM `in_valueset` reads the C++ g_valueset_cache global — NOT a
 * SQL table. Desktop FHIRDataLoader bridges table→cache via
 * `cql_valueset_cache_add`; the browser must do the same over
 * duckdb-wasm using the SAME registered UDF surface:
 *   cql_valueset_cache_clear() → BOOLEAN
 *   cql_valueset_cache_add(url, system, code) → BOOLEAN
 * Rows stage through the escaped-VALUES temp-table pattern (consistency
 * with resource staging), then ONE vectorized SELECT drives the adds —
 * per-row UDF round-trips would freeze the worker for seconds at real
 * ValueSet sizes.
 */

export interface ValuesetRow {
  url: string;
  system: string;
  code: string;
}

export interface ValuesetFlattenResult {
  rows: ValuesetRow[];
  /** Non-fatal flatten diagnostics surfaced in the TerminologyPane. */
  warnings: string[];
}

/** Empty ValueSets seed a sentinel row so membership is deterministic
 *  FALSE (url known, code never matches) instead of NULL — the empty
 *  cache would leave the url unknown and 3VL-poison comparisons. */
const EMPTY_SENTINEL_CODE = "__EMPTY_VALUESET__";

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/**
 * Flatten ValueSet resources to (url, system, code) rows, mirroring the
 * desktop loader's `_extract_codes_from_valueset_resource` semantics:
 * - compose.include[].concept[] and flat top-level codes[]
 * - expansion.contains[] when compose is absent
 * - codes WITHOUT a string system are SKIPPED with a warning (desktop
 *   boundary raises; the browser warns and continues)
 * - compose.exclude is NOT applied (documented desktop limitation — a
 *   warning is surfaced so authors are not silently surprised)
 */
export function valuesetToRows(
  valuesets: Array<Record<string, unknown>>,
): ValuesetFlattenResult {
  const rows: ValuesetRow[] = [];
  const warnings: string[] = [];
  const seen = new Set<string>();
  const push = (url: string, system: string, code: string) => {
    const key = `${url}\u0000${system}\u0000${code}`;
    if (seen.has(key)) return;
    seen.add(key);
    rows.push({ url, system, code });
  };

  for (const vs of valuesets) {
    const url = typeof vs.url === "string" ? vs.url : null;
    if (!url) {
      warnings.push("ValueSet without a url skipped (cannot seed the cache)");
      continue;
    }
    let added = 0;
    let excluded = false;

    // Desktop loader parity (fhir_loader._extract_codes_from_valueset_
    // resource): expansion.contains FIRST, then compose.include.concept,
    // as a UNION (dedup via the push() seen-set). VSAC sets are often
    // expansion-only while compose carries system-wide/valueSet-import
    // includes with no enumerated concepts.
    const expansion = isObj(vs.expansion) ? vs.expansion : null;
    const contains = expansion?.contains;
    if (Array.isArray(contains)) {
      for (const c of contains) {
        if (!isObj(c)) continue;
        const code = typeof c.code === "string" ? c.code : null;
        const system = typeof c.system === "string" ? c.system : null;
        if (!code) continue;
        if (!system) {
          warnings.push(
            `${url}: expansion code '${code}' skipped — no system`,
          );
          continue;
        }
        push(url, system, code);
        added += 1;
      }
    }

    const compose = isObj(vs.compose) ? vs.compose : null;
    const include = compose?.include;
    if (Array.isArray(include)) {
      for (const inc of include) {
        if (!isObj(inc)) continue;
        const system = typeof inc.system === "string" ? inc.system : null;
        const concept = inc.concept;
        if (Array.isArray(concept)) {
          for (const c of concept) {
            if (!isObj(c)) continue;
            const code = typeof c.code === "string" ? c.code : null;
            if (!code) continue;
            if (!system) {
              warnings.push(
                `${url}: concept code '${code}' skipped — no system on the include`,
              );
              continue;
            }
            push(url, system, code);
            added += 1;
          }
        } else if (system) {
          // include w/ system but no concept list: nothing to enumerate
          // (filter/valueSet imports are out of scope — warned below).
          const hasAdvanced =
            "filter" in inc || "valueSet" in inc || "group" in inc;
          if (hasAdvanced) {
            warnings.push(
              `${url}: compose.include with filter/valueSet imports is not expanded`,
            );
          }
        }
      }
      if (Array.isArray(compose?.exclude)) {
        excluded = true;
      }
    }

    if (excluded) {
      warnings.push(
        `${url}: compose.exclude is not applied (known engine boundary)`,
      );
    }
    if (added === 0) {
      // Deterministic-FALSE sentinel (never 3VL NULL).
      push(url, "urn:cleanroom:empty", EMPTY_SENTINEL_CODE);
    }
  }
  return { rows, warnings };
}

export function sqlStr(v: string): string {
  return `'${v.replace(/'/g, "''")}'`;
}

/**
 * Stage rows + drive cql_valueset_cache_add vectorized. Returns flatten
 * warnings for UI surfacing; throws on SQL failure (eval aborts loudly).
 */
export async function seedValuesetCache(
  rows: ValuesetRow[],
  runRaw: (sql: string) => Promise<unknown>,
): Promise<void> {
  if (!rows.length) {
    await runRaw("SELECT cql_valueset_cache_clear()");
    return;
  }
  const values = rows
    .map((r) => `(${sqlStr(r.url)}, ${sqlStr(r.system)}, ${sqlStr(r.code)})`)
    .join(", ");
  const stmts = [
    "SELECT cql_valueset_cache_clear()",
    "CREATE OR REPLACE TEMP TABLE __cleanroom_vs_stage (url VARCHAR, system VARCHAR, code VARCHAR)",
    `INSERT INTO __cleanroom_vs_stage VALUES ${values}`,
    "SELECT cql_valueset_cache_add(url, system, code) FROM __cleanroom_vs_stage",
    "DROP TABLE __cleanroom_vs_stage",
  ];
  for (const stmt of stmts) {
    await runRaw(stmt);
  }
}
