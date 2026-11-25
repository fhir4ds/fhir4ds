/**
 * ValueSet → engine cache bridge (browser side) — SHARED across the web apps.
 *
 * The WASM `in_valueset` UDF reads the C++ `g_valueset_cache` global, NOT a SQL
 * table. Desktop `FHIRDataLoader` bridges table→cache via
 * `cql_valueset_cache_add`; the browser must do the same over duckdb-wasm using
 * the SAME registered UDF surface:
 *   cql_valueset_cache_clear() → BOOLEAN
 *   cql_valueset_cache_add(url, system, code) → BOOLEAN
 *   cql_valueset_cache_size() → BIGINT
 * Rows stage through the escaped-VALUES temp-table pattern (consistency with
 * resource staging), then ONE vectorized SELECT drives the adds — per-row UDF
 * round-trips would freeze the worker for seconds at real ValueSet sizes.
 *
 * Consumers (all four apps import this ONE module; do not fork it):
 *   - web/cql-cleanroom  (reference implementation, datasets carry ValueSets)
 *   - web/wasm-demo      (sample data + uploaded/SMART resources)
 *   - web/cql-clinic     (lesson fixtures)
 *
 * SILENCE IS THE BUG: when a translated query references a ValueSet that was
 * never seeded, `in_valueset` returns SQL NULL and every population reads as
 * empty — a wrong answer with no error. `collectValuesetUrls()` +
 * `missingValuesetUrls()` exist so each app can surface that state LOUDLY
 * instead of reporting "no patients".
 */

export interface ValuesetRow {
  url: string;
  system: string;
  code: string;
}

export interface ValuesetFlattenResult {
  rows: ValuesetRow[];
  /** Non-fatal flatten diagnostics surfaced in the valueset editor. */
  warnings: string[];
}

/** Empty ValueSets seed a sentinel row so membership is deterministic
 *  FALSE (url known, code never matches) instead of NULL — the empty
 *  cache would leave the url unknown and 3VL-poison comparisons. */
export const EMPTY_SENTINEL_CODE = "__EMPTY_VALUESET__";

export function isObj(v: unknown): v is Record<string, unknown> {
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

/** The FHIR `ValueSet` resources carried by a resource collection (dataset,
 *  lesson fixtures, uploaded bundle, SMART patient data). */
export function valuesetResourcesOf(
  resources: ReadonlyArray<Record<string, unknown>>,
): Array<Record<string, unknown>> {
  return resources.filter((r) => r && r.resourceType === "ValueSet");
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

/** ValueSet membership UDF names the CQL translator can emit. */
const VALUESET_UDF_NAMES = [
  "fhirpath_equivalent_in_valueset",
  "cql_equivalent_in_valueset",
  "fhirpath_in_valueset",
  "in_valueset",
];

/** Split a SQL argument list on top-level commas (string literals respected). */
function splitTopLevelArgs(text: string): string[] {
  const args: string[] = [];
  let cur = "";
  let depth = 0;
  let inStr = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inStr) {
      if (ch === "'") {
        if (text[i + 1] === "'") {
          cur += "''";
          i += 1;
          continue;
        }
        inStr = false;
      }
      cur += ch;
      continue;
    }
    if (ch === "'") {
      inStr = true;
      cur += ch;
    } else if (ch === "(") {
      depth += 1;
      cur += ch;
    } else if (ch === ")") {
      depth -= 1;
      cur += ch;
    } else if (ch === "," && depth === 0) {
      args.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  if (cur.trim().length) args.push(cur);
  return args;
}

/** Unquote a SQL string literal; returns null when the arg is not a literal. */
function literalStringOf(arg: string): string | null {
  const trimmed = arg.trim();
  if (trimmed.length < 2 || trimmed[0] !== "'" || trimmed[trimmed.length - 1] !== "'") {
    return null;
  }
  return trimmed.slice(1, -1).replace(/''/g, "'");
}

/**
 * ValueSet URLs referenced by a translated query.
 *
 * `in_valueset(resource, path, '<url>')` (and its equivalent/fhirpath aliases)
 * is the ONLY way a translation asks the engine for valueset membership, so the
 * literal URL set is exactly the set of ValueSets the query needs loaded.
 */
export function collectValuesetUrls(sqlText: string): string[] {
  if (!sqlText) return [];
  const urls = new Set<string>();
  for (const name of VALUESET_UDF_NAMES) {
    let searchFrom = 0;
    for (;;) {
      const at = sqlText.indexOf(name, searchFrom);
      if (at === -1) break;
      searchFrom = at + name.length;
      // Whole-identifier match only (skip `_in_valueset`, `xin_valueset(`).
      const before = at === 0 ? "" : sqlText[at - 1];
      if (before && /[A-Za-z0-9_]/.test(before)) continue;
      let i = searchFrom;
      while (i < sqlText.length && /\s/.test(sqlText[i])) i += 1;
      if (sqlText[i] !== "(") continue;
      // Walk to the matching close paren.
      let depth = 0;
      let inStr = false;
      let end = -1;
      for (let j = i; j < sqlText.length; j++) {
        const ch = sqlText[j];
        if (inStr) {
          if (ch === "'") {
            if (sqlText[j + 1] === "'") {
              j += 1;
              continue;
            }
            inStr = false;
          }
          continue;
        }
        if (ch === "'") inStr = true;
        else if (ch === "(") depth += 1;
        else if (ch === ")") {
          depth -= 1;
          if (depth === 0) {
            end = j;
            break;
          }
        }
      }
      if (end === -1) continue;
      const args = splitTopLevelArgs(sqlText.slice(i + 1, end));
      const url = literalStringOf(args[args.length - 1] ?? "");
      if (url) urls.add(url);
      searchFrom = end;
    }
  }
  return [...urls];
}

/**
 * Referenced ValueSet URLs that were never seeded into the engine cache.
 * A non-empty result means the query cannot answer membership truthfully:
 * `in_valueset` returns NULL for unloaded URLs, so populations read empty.
 */
export function missingValuesetUrls(
  sqlText: string,
  loadedUrls: Iterable<string>,
): string[] {
  const loaded = new Set(loadedUrls);
  return collectValuesetUrls(sqlText).filter((url) => !loaded.has(url));
}

/**
 * Human-facing explanation for an unseeded-valueset run. Kept here so all
 * apps phrase the same failure the same way (silence is the bug).
 */
export function valuesetWarningMessage(urls: string[]): string {
  if (!urls.length) return "";
  const list = urls.join(", ");
  return (
    `${urls.length} ValueSet${urls.length === 1 ? "" : "s"} used by this query ` +
    `${urls.length === 1 ? "is" : "are"} not loaded in the browser engine ` +
    `(${list}). ValueSet membership returns UNKNOWN (SQL NULL) for unloaded ` +
    `sets, so populations can read as empty. Load the ValueSet resource(s) ` +
    `with the dataset, or pick a query that does not use them.`
  );
}
