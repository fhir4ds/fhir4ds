/**
 * MADiE measure-package export (M3) — mirrors packaging-utility layout:
 *   <name>-v<version>.zip
 *   ├── cql/<Library>-<version>.cql
 *   ├── resources/measure-<name>-<version>.json
 *   └── resources/library-<name>-<version>.json
 *
 * - Libraries = the DEPENDENCY CLOSURE of the primary (not every tab).
 * - Each closure library also ships as a FHIR Library resource carrying
 *   content[text/cql] (base64 not required; MADiE writes plain text).
 * - ValueSets referenced by closure libraries ride the Measure-adjacent
 *   resources/ dir as valueset-<id>.json.
 */
import { zipSync } from "fflate";

const enc = (s: string) => new TextEncoder().encode(s);

function libVersion(text: string): string {
  const m = text.match(/^\s*library\s+[A-Za-z][A-Za-z0-9_]*\s+version\s+'([^']+)'/m);
  return m ? m[1] : "1.0.0";
}

function libName(text: string): string | null {
  const m = text.match(/^\s*library\s+([A-Za-z][A-Za-z0-9_]*)/m);
  return m ? m[1] : null;
}

/** Valueset declarations ('urn:...' urls) across the closure's CQL. */
function declaredValuesets(texts: string[]): string[] {
  const urls = new Set<string>();
  for (const text of texts) {
    for (const m of text.matchAll(/valueset\s+"[^"]+"\s*:\s*'([^']+)'/g)) {
      urls.add(m[1]);
    }
  }
  return [...urls];
}

export function exportMadiePackage(opts: {
  libraries: Array<{ name: string; text: string }>;
  primaryName: string;
  measure: Record<string, unknown>;
  valuesets?: Array<Record<string, unknown>>;
}): Uint8Array {
  const { measure } = opts;
  // 1. Closure of the primary (client-side include walk).
  const byName = new Map(opts.libraries.map((l) => [l.name, l]));
  const primary = byName.get(opts.primaryName) ?? opts.libraries[0];
  const closure: Array<{ name: string; text: string }> = [];
  const seen = new Set<string>();
  const queue = [primary];
  while (queue.length) {
    const lib = queue.shift()!;
    if (seen.has(lib.name)) continue;
    seen.add(lib.name);
    closure.push(lib);
    for (const m of lib.text.matchAll(/include\s+([A-Za-z][A-Za-z0-9_]*)/g)) {
      const dep = byName.get(m[1]);
      if (dep && !seen.has(dep.name)) queue.push(dep);
    }
  }

  const measureName = String(measure.name ?? "CleanroomMeasure");
  const measureVersion = String(measure.version ?? "1.0.0");
  const files: Record<string, Uint8Array> = {};

  // 2. cql/ files + resources/library-*.json for the closure.
  for (const lib of closure) {
    const name = libName(lib.text) ?? lib.name;
    const version = libVersion(lib.text);
    files[`cql/${name}-${version}.cql`] = enc(lib.text);
    files[`resources/library-${name}-${version}.json`] = enc(
      JSON.stringify(
        {
          resourceType: "Library",
          name,
          version,
          status: "draft",
          type: {
            coding: [{ system: "http://terminology.hl7.org/CodeSystem/library-type", code: "logic-library" }],
          },
          content: [{ contentType: "text/cql", data: lib.text }],
        },
        null,
        2,
      ),
    );
  }

  // 3. The Measure — with library[] rewritten to the closure urns,
  //    primary first (importers resolve Measure.library[0]).
  const libraryUrls = closure.map(
    (l) => `urn:cleanroom:lib:${libName(l.text) ?? l.name}`,
  );
  const measureOut = { ...measure, library: libraryUrls };
  files[`resources/measure-${measureName}-${measureVersion}.json`] = enc(
    JSON.stringify(measureOut, null, 2),
  );

  // 4. ValueSets referenced by the closure.
  const referenced = new Set(declaredValuesets(closure.map((l) => l.text)));
  for (const vs of opts.valuesets ?? []) {
    const url = typeof vs.url === "string" ? vs.url : null;
    if (!url || !referenced.has(url)) continue;
    const id = typeof vs.id === "string" && vs.id ? vs.id : url.split(/[/:]/).filter(Boolean).pop() ?? "vs";
    files[`resources/valueset-${id}.json`] = enc(JSON.stringify(vs, null, 2));
  }

  return zipSync(files);
}
