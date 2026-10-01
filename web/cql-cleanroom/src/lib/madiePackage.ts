/**
 * MADiE measure-package import (M2).
 *
 * Reads the export layout produced by MADiE's packaging-utility:
 *   <name>.zip
 *   ├── cql/<LibraryName>-<version>.cql        (plain CQL)
 *   ├── resources/measure-<name>-<version>.json (FHIR Measure)
 *   └── resources/library-<name>-<version>.json (FHIR Library w/ content)
 *
 * Rules:
 * - CQL files become library tabs, ordered main-first per
 *   Measure.library[0] when resolvable (falls back to cql/ order).
 * - The Measure resource (JSON preferred; XML accepted for Measure
 *   reading is out of scope v1) becomes the workspace Measure.
 * - Library resources' content[text/cql] is ignored when a matching
 *   cql/ file exists (cql/ is the authored source of truth).
 * - ValueSets referenced by the Measure's libraries but not packaged
 *   are surfaced as unsourced (the Terminology pane already handles
 *   that state).
 */

import { unzipSync } from "fflate";

export interface MadiePackage {
  libraries: Array<{ name: string; text: string }>;
  measure: Record<string, unknown> | null;
  /** Primary library name (Measure.library[0] resolution). */
  primary: string | null;
  warnings: string[];
}

function libNameFromCql(text: string): string | null {
  const m = text.match(/^\s*library\s+([A-Za-z][A-Za-z0-9_]*)/m);
  return m ? m[1] : null;
}

/** `urn:cleanroom:lib:X` | `X` | `http://.../Library/X` → X (best effort). */
function canonicalTail(url: string): string | null {
  if (url.startsWith("urn:cleanroom:lib:")) {
    return url.slice("urn:cleanroom:lib:".length) || null;
  }
  const seg = url.split("/").filter(Boolean);
  if (seg.length >= 2 && seg[seg.length - 2] === "Library") {
    return seg[seg.length - 1].split("|")[0] || null;
  }
  return null;
}

export function importMadiePackage(bytes: Uint8Array): MadiePackage {
  const warnings: string[] = [];
  const files = unzipSync(bytes);
  const decode = (b: Uint8Array) => new TextDecoder().decode(b);

  // 1. cql/ files → libraries
  const libraries: Array<{ name: string; text: string }> = [];
  const cqlKeys = Object.keys(files)
    .filter((k) => k.startsWith("cql/") && k.endsWith(".cql"))
    .sort();
  for (const key of cqlKeys) {
    const text = decode(files[key]);
    const name = libNameFromCql(text);
    if (!name) {
      warnings.push(`${key}: no library declaration — skipped`);
      continue;
    }
    if (libraries.some((l) => l.name === name)) {
      warnings.push(`${key}: duplicate library name ${name} — first wins`);
      continue;
    }
    libraries.push({ name, text });
  }

  // 2. resources/measure-*.json → the Measure
  let measure: Record<string, unknown> | null = null;
  const measureKeys = Object.keys(files)
    .filter((k) => k.startsWith("resources/") && k.includes("measure-") && k.endsWith(".json"))
    .sort();
  for (const key of measureKeys) {
    try {
      const parsed = JSON.parse(decode(files[key]));
      if (parsed?.resourceType === "Measure") {
        measure = parsed;
        break;
      }
    } catch (e) {
      warnings.push(`${key}: invalid JSON — skipped`);
    }
  }
  if (!measure && measureKeys.length === 0) {
    warnings.push("no resources/measure-*.json found in package");
  }

  // 3. Library resources: backfill any library lacking a cql/ twin.
  const libResKeys = Object.keys(files)
    .filter((k) => k.startsWith("resources/") && k.includes("library-") && k.endsWith(".json"))
    .sort();
  for (const key of libResKeys) {
    try {
      const parsed = JSON.parse(decode(files[key]));
      if (parsed?.resourceType !== "Library") continue;
      const cqlContent = (parsed.content ?? []).find(
        (c: Record<string, unknown>) => c?.contentType === "text/cql" && typeof c.data === "string",
      );
      if (!cqlContent) continue;
      const text = cqlContent.data;
      const name = libNameFromCql(text) ?? String(parsed.name ?? "");
      if (!name) continue;
      if (libraries.some((l) => l.name === name)) continue; // cql/ wins
      libraries.push({ name, text });
    } catch {
      warnings.push(`${key}: invalid JSON — skipped`);
    }
  }

  // 4. Primary: Measure.library[0] tail → matching tab; else first cql/.
  let primary: string | null = libraries[0]?.name ?? null;
  const libRefs = (measure?.library as string[] | undefined) ?? [];
  if (libRefs.length) {
    const tail = canonicalTail(libRefs[0]);
    if (tail && libraries.some((l) => l.name === tail)) {
      primary = tail;
    } else if (tail) {
      warnings.push(
        `Measure.library[0] (${libRefs[0]}) has no matching tab — using ${primary}`,
      );
    }
  }

  // 5. Main-first ordering (MADiE convention).
  if (primary) {
    const idx = libraries.findIndex((l) => l.name === primary);
    if (idx > 0) {
      const [mainLib] = libraries.splice(idx, 1);
      libraries.unshift(mainLib);
    }
  }

  return { libraries, measure, primary, warnings };
}
